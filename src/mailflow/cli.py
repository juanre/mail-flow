# ABOUTME: Command-line interface for mailflow email processing workflows
# ABOUTME: Provides commands for processing, searching, stats, and Gmail integration
"""mailflow command-line interface"""

import logging
import sys
from pathlib import Path

import click

from mailflow.config import Config
from mailflow.gmail_api import poll_and_process as gmail_poll
from mailflow.logging_config import setup_logging
from mailflow.models import DataStore, WorkflowDefinition
from mailflow.process import process as process_email
from mailflow.processed_emails_tracker import ProcessedEmailsTracker

logger = logging.getLogger(__name__)


@click.group(invoke_without_command=True)
@click.pass_context
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.option(
    "--llm/--no-llm", default=None, help="Enable/disable LLM classification (overrides config)"
)
@click.option("--llm-model", default=None, help="LLM model alias: fast, balanced, or deep")
@click.option("--force", is_flag=True, help="Reprocess already processed emails")
def cli(ctx, debug, llm, llm_model, force):
    """mailflow - Smart Email Processing for Mutt

    When invoked without a subcommand, processes email from stdin.
    """
    # Store options in context for process_stdin to use
    ctx.ensure_object(dict)
    ctx.obj["llm"] = llm
    ctx.obj["llm_model"] = llm_model
    ctx.obj["force"] = force

    # Setup logging
    log_level = "DEBUG" if debug else "INFO"
    setup_logging(log_level)

    # If no subcommand, process email from stdin
    if ctx.invoked_subcommand is None:
        process_stdin()


@click.pass_context
def process_stdin(ctx):
    """Process email from stdin (default behavior for mutt integration)"""
    try:
        email_content = sys.stdin.read()
        if not email_content:
            logger.error("No email content received from stdin")
            sys.exit(1)

        # Get options from context
        llm_enabled = ctx.obj.get("llm")
        llm_model = ctx.obj.get("llm_model")
        force = ctx.obj.get("force", False)

        process_email(email_content, llm_enabled=llm_enabled, llm_model=llm_model, force=force)
    except KeyboardInterrupt:
        print("\n✗ Cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to process email: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.option("--query", "query", default="", help="Gmail search query (e.g., label:INBOX)")
@click.option("--label", "label", default=None, help="Only process messages with this Gmail label")
@click.option(
    "--processed-label", default="mailflow/processed", help="Label to add after processing"
)
@click.option("--max-results", default=20, help="Maximum Gmail messages to process per run")
@click.option("--remove-from-inbox", is_flag=True, help="Remove from INBOX after processing")
def gmail(query, label, processed_label, max_results, remove_from_inbox):
    """Process emails directly from Gmail via the Gmail API.

    Requirements:
      - Place OAuth client JSON at ~/.config/mailflow/gmail_client_secret.json
      - Install dependencies: uv add google-api-python-client google-auth google-auth-oauthlib
    """
    config = Config()
    try:
        count = gmail_poll(
            config,
            query=query,
            label=label,
            processed_label=processed_label,
            max_results=max_results,
            remove_from_inbox=remove_from_inbox,
        )
        click.echo(f"\n✓ Processed {count} Gmail message(s)")
    except RuntimeError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    except Exception as e:
        logger.exception("Gmail processing failed")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("directory", type=click.Path(exists=True))
@click.option("--llm/--no-llm", default=None, help="Enable/disable LLM (overrides config)")
@click.option("--llm-model", default=None, help="LLM model: fast, balanced, or deep")
@click.option(
    "--auto-threshold", default=0.85, type=float, help="Auto-process above this confidence"
)
@click.option("--dry-run", is_flag=True, help="Preview without executing workflows")
@click.option("--max-emails", default=None, type=int, help="Limit number of emails to process")
@click.option("--force", is_flag=True, help="Reprocess already processed emails")
def batch(directory, llm, llm_model, auto_threshold, dry_run, max_emails, force):
    """Process multiple emails from a directory

    Processes all .eml files in DIRECTORY and subdirectories.
    Emails above auto-threshold are processed automatically.
    Others are presented for review.

    Example:
        mailflow batch ~/mail/archive --llm --auto-threshold 0.9
    """
    from pathlib import Path

    from mailflow.email_extractor import EmailExtractor
    from mailflow.hybrid_classifier import HybridClassifier
    from mailflow.llm_classifier import LLMClassifier
    from mailflow.models import DataStore
    from mailflow.similarity import SimilarityEngine

    config = Config()

    # Override LLM settings from CLI
    if llm is not None:
        config.settings["llm"]["enabled"] = llm
    if llm_model is not None:
        config.settings["llm"]["model_alias"] = llm_model

    data_store = DataStore(config)
    extractor = EmailExtractor()
    similarity_engine = SimilarityEngine(config)

    # Initialize processed emails tracker
    tracker = ProcessedEmailsTracker(config)

    # Setup hybrid classifier if LLM enabled
    hybrid_classifier = None
    if config.settings.get("llm", {}).get("enabled", False):
        try:
            model_alias = config.settings["llm"].get("model_alias", "balanced")
            llm_classifier = LLMClassifier(model_alias=model_alias)
            hybrid_classifier = HybridClassifier(similarity_engine, llm_classifier)
            click.echo(f"✓ LLM enabled (model: {model_alias})")
        except Exception as e:
            click.echo(f"⚠️  LLM setup failed: {e}, using similarity only", err=True)

    # Find email files
    directory_path = Path(directory).expanduser()
    email_files = list(directory_path.glob("**/*.eml"))

    if max_emails:
        email_files = email_files[:max_emails]

    if not email_files:
        click.echo(f"No .eml files found in {directory}")
        return

    click.echo(f"\nFound {len(email_files)} emails to process")

    # Cost warning for LLM
    if hybrid_classifier:
        estimated_llm_calls = len(email_files) * 0.2  # Estimate 20% need LLM
        estimated_cost = estimated_llm_calls * 0.003  # $0.003 per call
        click.echo(f"⚠️  Estimated LLM cost: ${estimated_cost:.2f} (assumes ~20% need LLM assist)")
        if not dry_run:
            if not click.confirm("Continue with processing?", default=True):
                click.echo("Cancelled by user")
                return

    if dry_run:
        click.echo("DRY RUN MODE - no workflows will be executed\n")

    stats = {"processed": 0, "auto": 0, "skipped": 0, "errors": 0}

    for i, email_file in enumerate(email_files, 1):
        try:
            # Read email content first
            with open(email_file, encoding="utf-8", errors="replace") as f:
                email_content = f.read()

            # Extract to get message_id
            email_data = extractor.extract(email_content)
            message_id = email_data.get("message_id")

            # Check if already processed (unless --force)
            if not force and tracker.is_processed(email_content, message_id):
                processed_info = tracker.get_processed_info(email_content, message_id)
                prev_workflow = (
                    processed_info.get("workflow_name", "unknown") if processed_info else "unknown"
                )
                click.echo(
                    f"[{i}/{len(email_files)}] ⊘ {email_file.name}: Already processed ({prev_workflow})"
                )
                stats["skipped"] += 1
                continue

            # Classify
            if hybrid_classifier:
                import asyncio

                result = asyncio.run(
                    hybrid_classifier.classify(
                        email_data, data_store.workflows, data_store.get_recent_criteria()
                    )
                )
                rankings = result["rankings"]
            else:
                rankings = similarity_engine.rank_workflows(
                    email_data["features"], data_store.get_recent_criteria(), top_n=5
                )

            if rankings:
                workflow_name, confidence, _ = rankings[0]

                # Progress display
                status = "✓" if confidence >= auto_threshold else "?"
                click.echo(
                    f"[{i}/{len(email_files)}] {status} {email_file.name}: {workflow_name} ({confidence:.0%})"
                )

                if confidence >= auto_threshold:
                    stats["auto"] += 1
                    if not dry_run:
                        # Execute the workflow
                        from mailflow.workflow import Workflows

                        workflow_def = data_store.workflows.get(workflow_name)
                        if workflow_def and workflow_def.action_type in Workflows:
                            try:
                                action_func = Workflows[workflow_def.action_type]
                                action_func(email_data, **workflow_def.action_params)

                                # Mark as processed
                                tracker.mark_as_processed(email_content, message_id, workflow_name)

                            except Exception as e:
                                click.echo(f"    Failed to execute workflow: {e}", err=True)
                                stats["errors"] += 1
                                stats["auto"] -= 1  # Don't count as auto-processed
                else:
                    # Would need review
                    stats["processed"] += 1
            else:
                click.echo(f"[{i}/{len(email_files)}] - {email_file.name}: No match")
                stats["skipped"] += 1

        except Exception as e:
            click.echo(f"[{i}/{len(email_files)}] ✗ {email_file.name}: Error - {e}", err=True)
            stats["errors"] += 1

    # Summary
    click.echo(f"\n{'='*60}")
    click.echo("Summary:")
    click.echo(f"  Auto-processed: {stats['auto']}")
    click.echo(f"  Need review: {stats['processed']}")
    click.echo(f"  Already processed (skipped): {stats['skipped']}")
    click.echo(f"  Errors: {stats['errors']}")
    click.echo(f"{'='*60}")
    if dry_run:
        click.echo("DRY RUN - No workflows were executed")
    else:
        click.echo("Processing complete")


@cli.command()
@click.option("--reset", is_flag=True, help="Reset configuration (backup existing)")
def init(reset):
    """Initialize mailflow configuration with default workflows"""
    # Initialize configuration
    click.echo("\nInitializing mailflow configuration...")
    config = Config()

    # Handle existing configuration
    if config.get_workflows_file().exists() and reset:
        backup_path = config.backup_file(config.get_workflows_file())
        click.echo(f"✓ Backed up existing workflows to {backup_path}")
    elif config.get_workflows_file().exists() and not reset:
        click.echo(f"Configuration already exists at {config.config_dir}")
        click.echo("Use --reset to backup and create fresh configuration")
        return
    data_store = DataStore(config)

    # Create only generic default workflows
    default_workflows = [
        {
            "name": "save-receipts",
            "description": "Save receipts and invoices as PDFs",
            "action_type": "save_pdf",
            "action_params": {
                "directory": "~/Documents/mailflow/receipts",
                "filename_template": "{date}-{from}-{subject}",
            },
        },
        {
            "name": "create-todo",
            "description": "Create a todo item from email",
            "action_type": "create_todo",
            "action_params": {"todo_file": "~/todos.txt"},
        },
    ]

    click.echo("\nCreating default workflows...")
    for workflow_data in default_workflows:
        try:
            workflow = WorkflowDefinition(**workflow_data)
            if workflow.name not in data_store.workflows:
                data_store.add_workflow(workflow)
                click.echo(f"  ✓ {workflow.name}: {workflow.description}")
        except Exception as e:
            click.echo(f"  ✗ Failed to create {workflow_data['name']}: {e}", err=True)

    # Show summary
    click.echo(f"\n✓ Configuration initialized at {config.config_dir}")
    click.echo(f"  Workflows: {len(data_store.workflows)}")
    click.echo(f"  Learning examples: {len(data_store.criteria_instances)}")

    click.echo("\n📝 Add to your .muttrc:")
    click.echo('  macro index,pager \\cp "<pipe-message>mailflow<enter>" "Process with mailflow"')
    click.echo("\n🚀 Press Ctrl-P in mutt to start processing emails!")

    # Show LLM setup instructions
    click.echo("\n🤖 Optional: Enable AI-Powered Classification")
    click.echo("  mailflow can use LLM to improve classification accuracy.")
    click.echo("")
    click.echo("  To enable:")
    click.echo("  1. Set up API key (NEVER commit to git!):")
    click.echo("     export ANTHROPIC_API_KEY=sk-ant-...")
    click.echo("     # Add to ~/.bashrc or ~/.zshrc, NOT to config.json")
    click.echo("     # or OPENAI_API_KEY or GOOGLE_GEMINI_API_KEY")
    click.echo("")
    click.echo("  2. Edit ~/.config/mailflow/config.json:")
    click.echo('     "llm": { "enabled": true }')
    click.echo("")
    click.echo("  3. (Optional) Initialize llmring:")
    click.echo("     llmring lock init")
    click.echo("")
    click.echo("  ⚠️  Security: Keep API keys in environment variables or .env file")
    click.echo("  Do NOT put API keys in config.json or commit them to git!")
    click.echo("")
    click.echo("  Cost: ~$0.003 per email with balanced model")
    click.echo("  See docs for details: https://github.com/juanre/mailflow")


@cli.command()
@click.option("--limit", "-n", default=10, help="Number of workflows to show")
def workflows(limit):
    """List available workflows"""
    config = Config()
    data_store = DataStore(config)

    click.echo(f"\nAvailable workflows ({len(data_store.workflows)} total):\n")

    for i, (name, workflow) in enumerate(data_store.workflows.items()):
        if i >= limit:
            remaining = len(data_store.workflows) - limit
            click.echo(f"\n... and {remaining} more")
            break

        click.echo(f"{name}:")
        click.echo(f"  {workflow.description}")
        click.echo(f"  Type: {workflow.action_type}")

        # Show relevant parameters
        params = workflow.action_params
        if "directory" in params:
            click.echo(f"  Directory: {params['directory']}")
        if "pattern" in params:
            click.echo(f"  Pattern: {params['pattern']}")
        if "filename_template" in params:
            click.echo(f"  Filename: {params['filename_template']}")
        click.echo()


@cli.command()
def stats():
    """Show learning statistics"""
    config = Config()
    data_store = DataStore(config)

    click.echo("\n📊 mailflow Statistics\n")
    click.echo(f"Total workflows: {len(data_store.workflows)}")
    click.echo(f"Total examples: {len(data_store.criteria_instances)}")

    # Count examples per workflow
    workflow_counts = {}
    for instance in data_store.criteria_instances:
        workflow_name = instance.workflow_name
        workflow_counts[workflow_name] = workflow_counts.get(workflow_name, 0) + 1

    if workflow_counts:
        click.echo("\nExamples per workflow:")
        for workflow, count in sorted(workflow_counts.items(), key=lambda x: x[1], reverse=True):
            click.echo(f"  {workflow}: {count}")

    # Show recent activity
    if data_store.criteria_instances:
        recent = sorted(data_store.criteria_instances, key=lambda x: x.timestamp, reverse=True)[:5]
        click.echo("\nRecent classifications:")
        for instance in recent:
            click.echo(
                f"  {instance.timestamp.strftime('%Y-%m-%d %H:%M')} - {instance.workflow_name}"
            )


@cli.command()
@click.argument("query", required=False)
@click.option("--directory", "-d", default="~/receipts", help="Directory to search")
@click.option("--limit", "-n", default=20, help="Maximum results")
@click.option("--type", "-t", help="Filter by document type (invoice, receipt, etc.)")
def search(query, directory, limit, type):
    """Search stored PDFs"""
    from mailflow.metadata_store import MetadataStore

    try:
        store = MetadataStore(Path(directory).expanduser())

        if type:
            results = store.search_by_type(type, limit)
            search_desc = f"type '{type}'"
        elif query:
            results = store.search(query, limit)
            search_desc = f"'{query}'"
        else:
            # Show recent PDFs without FTS
            results = store.search("", limit)
            search_desc = "recent PDFs"

        if not results:
            click.echo(f"No results found for {search_desc}")
            return

        click.echo(f"\nFound {len(results)} results for {search_desc}:\n")

        for i, result in enumerate(results, 1):
            click.echo(f"{i}. {result['filename']}")
            click.echo(f"   From: {result['email_from']}")
            click.echo(f"   Date: {result['email_date']}")
            if result.get("document_type"):
                click.echo(f"   Type: {result['document_type']}")
            click.echo(f"   Path: {result['filepath']}")
            click.echo()

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("filepath")
def data(filepath):
    """Show all database information for a PDF file

    FILEPATH can be either a full path or just the filename.
    If only a filename is provided, it will search all workflow directories.

    Examples:
        mailflow data receipts/2025/2025-07-29-dropbox.com-subscription.pdf
        mailflow data 2025-07-29-dropbox.com-subscription.pdf
    """
    import json

    from mailflow.metadata_store import MetadataStore

    # Try different workflow directories
    config = Config()
    data_store = DataStore(config)

    # Extract base directories from workflows
    base_dirs = set()
    for workflow in data_store.workflows.values():
        if workflow.action_type == "save_pdf" and "directory" in workflow.action_params:
            dir_path = Path(workflow.action_params["directory"]).expanduser()
            # Add the actual workflow directory as a base dir
            base_dirs.add(dir_path)

    # Also try common locations
    base_dirs.add(Path("~/Documents/mailflow").expanduser())
    base_dirs.add(Path("~/receipts").expanduser())

    result = None
    found_in_store = None

    # Try each base directory
    for base_dir in base_dirs:
        if not base_dir.exists():
            continue

        try:
            store = MetadataStore(str(base_dir))
            result = store.get_by_filepath(filepath)
            if result:
                found_in_store = base_dir
                break
        except Exception:
            continue

    if not result:
        click.echo(f"No data found for: {filepath}", err=True)
        click.echo("\nTried searching in:", err=True)
        for base_dir in sorted(base_dirs):
            click.echo(f"  - {base_dir}", err=True)
        sys.exit(1)

    # Format and display the data
    click.echo(f"\n📄 PDF Metadata for: {result['filename']}")
    click.echo(f"Database location: {found_in_store}")
    click.echo("=" * 60)

    # File information
    click.echo("\n📁 File Information:")
    click.echo(f"  Filename: {result['filename']}")
    click.echo(f"  Path: {result['filepath']}")
    click.echo(f"  Size: {result['file_size']:,} bytes ({result['file_size'] / 1024:.1f} KB)")
    click.echo(f"  Hash: {result['file_hash']}")
    click.echo(f"  Saved: {result['saved_at']}")

    # Email metadata
    click.echo("\n📧 Email Metadata:")
    click.echo(f"  From: {result['email_from']}")
    click.echo(f"  To: {result['email_to']}")
    click.echo(f"  Subject: {result['email_subject']}")
    click.echo(f"  Date: {result['email_date']}")
    click.echo(f"  Message ID: {result['email_message_id']}")

    # PDF information
    click.echo("\n📑 PDF Information:")
    click.echo(f"  Type: {result['pdf_type']} (attachment/converted)")
    if result["pdf_original_filename"]:
        click.echo(f"  Original filename: {result['pdf_original_filename']}")
    if result["pdf_page_count"]:
        click.echo(f"  Page count: {result['pdf_page_count']}")

    # Document classification
    click.echo("\n🏷️  Document Classification:")
    click.echo(f"  Type: {result['document_type'] or 'Not classified'}")
    click.echo(f"  Category: {result['document_category'] or 'Not categorized'}")

    # Workflow information
    click.echo("\n⚙️  Workflow Information:")
    click.echo(f"  Workflow: {result['workflow_name']}")
    if result["confidence_score"]:
        click.echo(f"  Confidence: {result['confidence_score']:.2f}")

    # Email headers (parsed JSON)
    if result["email_headers"]:
        try:
            headers = json.loads(result["email_headers"])
            if headers:
                click.echo("\n📨 Email Headers:")
                for key, value in headers.items():
                    if key.lower() not in ["from", "to", "subject", "date", "message-id"]:
                        click.echo(f"  {key}: {value}")
        except:
            pass

    # Document info (parsed JSON)
    if result["document_info"]:
        try:
            doc_info = json.loads(result["document_info"])
            if doc_info:
                click.echo("\n📊 Extracted Document Information:")
                for key, value in doc_info.items():
                    click.echo(f"  {key}: {value}")
        except:
            pass

    # Structured metadata (parsed JSON)
    if result.get("metadata"):
        try:
            metadata = json.loads(result["metadata"])
            if metadata:
                click.echo("\n💼 Structured Metadata:")
                for key, value in metadata.items():
                    click.echo(f"  {key}: {value}")
        except:
            pass

    # Text content preview
    if result["pdf_text_content"]:
        click.echo("\n📝 PDF Text Content (first 500 chars):")
        text_preview = result["pdf_text_content"][:500].strip()
        if len(result["pdf_text_content"]) > 500:
            text_preview += "..."
        click.echo(f"  {text_preview}")

    if result["email_body_text"] and not result["pdf_text_content"]:
        click.echo("\n📝 Email Body Text (first 500 chars):")
        text_preview = result["email_body_text"][:500].strip()
        if len(result["email_body_text"]) > 500:
            text_preview += "..."
        click.echo(f"  {text_preview}")

    click.echo("\n" + "=" * 60)


@cli.command()
def setup_workflows():
    """Interactive workflow setup assistant

    Guides you through creating custom workflows for organizing emails.
    Creates workflows for different entities (companies, personal) and
    document types (expenses, tax documents, general documents).
    """
    config = Config()
    data_store = DataStore(config)

    click.echo("\n📋 Workflow Setup Assistant")
    click.echo("=" * 60)
    click.echo("\nThis will help you create workflows for organizing emails.")
    click.echo("You can define entities (companies, personal) and document types.")
    click.echo("")

    # Ask about entities
    click.echo("Step 1: Define your entities")
    click.echo("Examples: business, personal, company-name, etc.")
    click.echo("Leave blank when done.\n")

    entities = []
    while True:
        entity_code = click.prompt(
            "Entity code (short, e.g., 'biz')", default="", show_default=False
        )
        if not entity_code:
            break
        entity_name = click.prompt(f"  Full name for '{entity_code}'", default=entity_code)
        entities.append((entity_code, entity_name))

    if not entities:
        click.echo("\n⚠️  No entities defined. Creating generic workflows only.")
        entities = [("general", "General")]

    # Ask about document types
    click.echo("\nStep 2: Define document types")
    click.echo("Examples: expense, tax-doc, invoice, receipt, etc.")
    click.echo("Leave blank when done.\n")

    doc_types = []
    while True:
        doc_code = click.prompt(
            "Document type code (e.g., 'expense')", default="", show_default=False
        )
        if not doc_code:
            break
        doc_desc = click.prompt(f"  Description for '{doc_code}'", default=doc_code + "s")
        doc_types.append((doc_code, doc_desc))

    if not doc_types:
        doc_types = [("doc", "documents")]

    # Create workflows
    click.echo(f"\nStep 3: Creating {len(entities) * len(doc_types)} workflows...")

    created_count = 0
    for entity_code, entity_name in entities:
        for doc_code, doc_desc in doc_types:
            workflow_name = f"{entity_code}-{doc_code}"
            workflow = WorkflowDefinition(
                name=workflow_name,
                description=f"Save {entity_name} {doc_desc}",
                action_type="save_pdf",
                action_params={
                    "directory": f"~/Documents/mailflow/{entity_code}/{doc_code}",
                    "filename_template": "{date}-{from}-{subject}",
                },
            )

            try:
                if workflow.name not in data_store.workflows:
                    data_store.add_workflow(workflow)
                    click.echo(f"  ✓ {workflow_name}: {workflow.description}")
                    created_count += 1
                else:
                    click.echo(f"  ⊘ {workflow_name}: Already exists")
            except Exception as e:
                click.echo(f"  ✗ {workflow_name}: Failed - {e}", err=True)

    # Create directories
    click.echo(f"\nCreating directories...")
    for entity_code, _ in entities:
        for doc_code, _ in doc_types:
            dir_path = Path(f"~/Documents/mailflow/{entity_code}/{doc_code}").expanduser()
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                click.echo(f"  ✓ {dir_path}")
            except Exception as e:
                click.echo(f"  ✗ Failed to create {dir_path}: {e}", err=True)

    # Summary
    click.echo(f"\n{'='*60}")
    click.echo(f"✓ Created {created_count} new workflows")
    click.echo(f"  Total workflows: {len(data_store.workflows)}")
    click.echo(f"\nWorkflows saved to: {config.config_dir / 'workflows.json'}")


@cli.command()
def version():
    """Show mailflow version"""
    from mailflow import __version__

    click.echo(f"mailflow version {__version__}")


if __name__ == "__main__":
    cli()
