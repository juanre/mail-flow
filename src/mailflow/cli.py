# ABOUTME: Command-line interface for mailflow email processing workflows
# ABOUTME: Provides commands for processing, searching, stats, and Gmail integration
"""mailflow command-line interface"""

import asyncio
import logging
import re
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from mailflow.config import Config
from mailflow.commands.index_search import register as register_index_commands
from mailflow.commands.gmail_batch_workflows import register as register_gmail_batch
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
    # Load environment from .env if present (for archivist/LLM/DB config)
    load_dotenv()

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

        asyncio.run(
            process_email(email_content, llm_enabled=llm_enabled, llm_model=llm_model, force=force)
        )
    except KeyboardInterrupt:
        print("\n✗ Cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to process email: {e}", exc_info=True)
        sys.exit(1)


@cli.command(name="archivist-metrics")
def archivist_metrics() -> None:
    """Show basic llm-archivist metrics (DB or dev)."""
    from mailflow.archivist_client import get_metrics

    try:
        metrics = asyncio.run(get_metrics())
    except Exception as exc:  # pragma: no cover - operational
        click.echo(f"Error fetching archivist metrics: {exc}", err=True)
        raise SystemExit(1)

    # Print a compact, human-readable summary
    mode = metrics.get("mode", "dev")
    decisions = metrics.get("decisions", metrics.get("decisions", 0))
    feedback = metrics.get("feedback", metrics.get("feedback", 0))
    click.echo(f"Archivist mode: {mode}")
    click.echo(f"Decisions: {decisions}")
    click.echo(f"Feedback: {feedback}")

    by_label = metrics.get("by_label") or {}
    if by_label:
        click.echo("\nDecisions by label:")
        for label, count in sorted(by_label.items(), key=lambda x: (-x[1], x[0])):
            click.echo(f"  {label}: {count}")

    advisor_top1 = metrics.get("advisor_top1") or {}
    if advisor_top1:
        click.echo("\nTop-1 advisor usage:")
        for name, count in sorted(advisor_top1.items(), key=lambda x: (-x[1], x[0])):
            click.echo(f"  {name}: {count}")


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
    asyncio.run(
        _batch_async(directory, llm, llm_model, auto_threshold, dry_run, max_emails, force)
    )


async def _batch_async(directory, llm, llm_model, auto_threshold, dry_run, max_emails, force):
    """Async implementation of batch processing."""
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
                result = await hybrid_classifier.classify(
                    email_data, data_store.workflows, data_store.get_recent_criteria()
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

                                # Intentionally no training here: auto mode should not
                                # feed classifiers without explicit review.

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


def _interactive_workflow_setup(config: Config, data_store: DataStore) -> tuple[int, int]:
    """Shared interactive workflow setup logic.

    Prompts user for entities and document types, creates workflows and directories.

    Args:
        config: Config instance
        data_store: DataStore instance

    Returns:
        tuple: (created_count, total_workflows)

    Raises:
        KeyboardInterrupt: If user cancels with Ctrl+C
        EOFError: If user cancels with Ctrl+D
    """
    click.echo("\n📋 Workflow Setup")
    click.echo("=" * 60)
    click.echo("\nThis will help you create workflows for organizing emails.")
    click.echo("You can define entities (companies, personal) and document types.")
    click.echo("")

    # Ask about entities
    click.echo("Step 1: Define your entities")
    click.echo("Examples: jro (Juan Reyero), tsm (TheStarMaps), gsk (GreaterSkies)")
    click.echo("Press Enter without input when done.\n")

    entities = []
    while True:
        entity_code = click.prompt(
            "Entity code (short, e.g., 'jro')", default="", show_default=False
        )
        if not entity_code:
            break

        # Validate entity code
        if not re.match(r'^[a-z0-9_-]+$', entity_code):
            click.echo("  ✗ Entity code must contain only lowercase letters, numbers, hyphens, and underscores")
            continue

        entity_name = click.prompt(f"  Full name for '{entity_code}'", default=entity_code)

        # Validate entity name length
        if not entity_name or len(entity_name) > 100:
            click.echo("  ✗ Entity name must be 1-100 characters")
            continue

        # Sanitize entity name (remove control characters, keep printable)
        entity_name = "".join(c for c in entity_name if c.isprintable())
        if not entity_name:
            click.echo("  ✗ Entity name contains no valid characters")
            continue

        entities.append((entity_code, entity_name))

    if not entities:
        click.echo("\n⚠️  No entities defined. Creating generic workflows only.")
        entities = [("general", "General")]

    # Ask about document types
    click.echo("\nStep 2: Define document types")
    click.echo("Examples: expense, tax-doc, invoice, receipt, doc")
    click.echo("Press Enter without input when done.\n")

    doc_types = []
    while True:
        doc_code = click.prompt(
            "Document type code (e.g., 'expense')", default="", show_default=False
        )
        if not doc_code:
            break

        # Validate doc code
        if not re.match(r'^[a-z0-9_-]+$', doc_code):
            click.echo("  ✗ Document type must contain only lowercase letters, numbers, hyphens, and underscores")
            continue

        doc_desc = click.prompt(
            f"  Description for '{doc_code}'",
            default=doc_code.replace('-', ' ')
        )

        # Validate description length
        if not doc_desc or len(doc_desc) > 200:
            click.echo("  ✗ Description must be 1-200 characters")
            continue

        # Sanitize description (remove control characters, keep printable)
        doc_desc = "".join(c for c in doc_desc if c.isprintable())
        if not doc_desc:
            click.echo("  ✗ Description contains no valid characters")
            continue

        doc_types.append((doc_code, doc_desc))

    if not doc_types:
        doc_types = [("doc", "documents")]

    # Confirmation for large batches
    workflow_count = len(entities) * len(doc_types)
    if workflow_count > 10:
        click.echo(f"\n⚠️  This will create {workflow_count} workflows and directories.")
        if not click.confirm("Continue?", default=True):
            click.echo("Cancelled")
            return (0, len(data_store.workflows))

    # Create workflows
    click.echo(f"\nStep 3: Creating {workflow_count} workflows...")

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
    failed_dirs = []
    for entity_code, _ in entities:
        for doc_code, _ in doc_types:
            dir_path = Path(f"~/Documents/mailflow/{entity_code}/{doc_code}").expanduser()
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                # Test that it's writable
                test_file = dir_path / ".mailflow_test"
                test_file.touch()
                test_file.unlink()
                click.echo(f"  ✓ {dir_path}")
            except PermissionError:
                click.echo(f"  ✗ Permission denied: {dir_path}", err=True)
                failed_dirs.append(str(dir_path))
            except Exception as e:
                click.echo(f"  ✗ Failed to create {dir_path}: {e}", err=True)
                failed_dirs.append(str(dir_path))

    if failed_dirs:
        click.echo(f"\n⚠️  Warning: {len(failed_dirs)} director(ies) could not be created")
        click.echo("These workflows may fail at runtime. Check permissions:")
        for d in failed_dirs:
            click.echo(f"  - {d}")

    return (created_count, len(data_store.workflows))


@cli.command()
@click.option("--reset", is_flag=True, help="Reset configuration (backup existing)")
def init(reset):
    """Initialize mailflow with interactive workflow setup

    Guides you through creating custom workflows for organizing emails.
    Creates workflows for different entities (companies, personal) and
    document types (expenses, tax documents, general documents).
    """
    # Initialize configuration
    click.echo("\n🚀 mailflow Initialization")
    click.echo("=" * 60)

    try:
        config = Config()
    except Exception as e:
        click.echo(f"\n✗ Failed to initialize config: {e}", err=True)
        click.echo("Check that you have write permissions to ~/.config/")
        sys.exit(1)

    # Handle existing configuration
    if config.get_workflows_file().exists() and reset:
        backup_path = config.backup_file(config.get_workflows_file())
        click.echo(f"✓ Backed up existing workflows to {backup_path}")
    elif config.get_workflows_file().exists() and not reset:
        click.echo(f"Configuration already exists at {config.config_dir}")
        click.echo("Use --reset to backup and create fresh configuration")
        return

    click.echo(f"✓ Configuration directory: {config.config_dir}")
    data_store = DataStore(config)

    # Interactive workflow setup with error handling
    try:
        created_count, total_workflows = _interactive_workflow_setup(config, data_store)
    except (KeyboardInterrupt, EOFError):
        click.echo("\n\n✗ Setup cancelled by user")
        click.echo("Run 'mailflow init' again to complete setup")
        sys.exit(0)
    except Exception as e:
        click.echo(f"\n✗ Setup failed: {e}", err=True)
        sys.exit(1)

    # Summary
    click.echo(f"\n{'='*60}")
    click.echo(f"✓ Created {created_count} new workflows")
    click.echo(f"  Total workflows: {total_workflows}")
    click.echo(f"  Config location: {config.config_dir}")

    click.echo("\n📝 Next Steps:")
    click.echo("  1. Add to your .muttrc:")
    click.echo('     macro index,pager \\cp "<pipe-message>mailflow<enter>" "Process with mailflow"')
    click.echo("\n  2. Press Ctrl-P in mutt to process emails")
    click.echo("\n  3. (Optional) Enable LLM for better classification:")
    click.echo("     export ANTHROPIC_API_KEY=sk-ant-...")
    click.echo("     Edit ~/.config/mailflow/config.json: \"llm\": { \"enabled\": true }")
    click.echo(f"\n💡 Tip: Run 'mailflow setup-workflows' anytime to add more workflows")


from mailflow.commands.gmail_batch_workflows import register as _register_gbw
_register_gbw(cli)


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
@click.argument("filepath")
def data(filepath):
    """Show indexed information for a document (by path or filename).

    FILEPATH can be a full path (endswith match on rel_path) or just the filename.
    Uses global indexes; run `mailflow index` first.
    """
    from mailflow.global_index import GlobalIndex

    cfg = Config()
    base = cfg.settings.get("archive", {}).get("base_path", "~/Archive")
    idx_path = Path(base).expanduser() / "indexes"
    gi = GlobalIndex(str(idx_path))

    # Try rel_path endswith match
    doc = None
    rel = Path(filepath).as_posix()
    with gi._conn() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE rel_path LIKE ? ORDER BY id DESC LIMIT 1",
            (f"%{rel}",),
        ).fetchone()
        if not row:
            # Try filename exact match
            name = Path(filepath).name
            row = conn.execute(
                "SELECT * FROM documents WHERE filename = ? ORDER BY id DESC LIMIT 1",
                (name,),
            ).fetchone()
        doc = dict(row) if row else None

    if not doc:
        click.echo(f"No indexed entry found for: {filepath}", err=True)
        sys.exit(1)

    click.echo(f"\nDocument: {doc['filename']}  ({doc['entity']})")
    click.echo("=" * 60)
    click.echo(f"Date: {doc['date']}")
    click.echo(f"Type: {doc['type']}")
    click.echo(f"Source: {doc['source']}")
    if doc.get("workflow"):
        click.echo(f"Workflow: {doc['workflow']}")
    if doc.get("category"):
        click.echo(f"Category: {doc['category']}")
    if doc.get("confidence") is not None:
        click.echo(f"Confidence: {doc['confidence']:.2f}")
    click.echo(f"Relative path: {doc['rel_path']}")
    click.echo(f"Size: {doc.get('size') or 0} bytes")
    click.echo(f"Hash: {doc.get('hash') or '-'}")
    try:
        origin = json.loads(doc.get("origin_json") or "{}")
    except Exception:
        origin = {}
    if origin:
        click.echo("\nOrigin:")
        for k, v in origin.items():
            if k == "classifier":
                continue
            click.echo(f"  {k}: {v}")
        if origin.get("classifier"):
            c = origin["classifier"]
            click.echo("\nClassifier:")
            click.echo(f"  suggestion={c.get('workflow_suggestion')} type={c.get('type')} category={c.get('category')} conf={c.get('confidence')}")




register_index_commands(cli)
register_gmail_batch(cli)

@cli.command()
def setup_workflows():
    """Interactive workflow setup assistant

    Add more workflows to your existing configuration.
    Use this after 'mailflow init' to create additional entity/document workflows.
    """
    config = Config()
    data_store = DataStore(config)

    click.echo("\n📋 Workflow Setup Assistant")
    click.echo("=" * 60)

    # Show existing workflows if any
    if data_store.workflows:
        click.echo(f"\n✓ You currently have {len(data_store.workflows)} workflow(s)")
        click.echo("Adding more workflows will merge with existing ones.")
        if not click.confirm("Continue?", default=True):
            return

    # Use shared interactive setup with error handling
    try:
        created_count, total_workflows = _interactive_workflow_setup(config, data_store)
    except (KeyboardInterrupt, EOFError):
        click.echo("\n\n✗ Setup cancelled by user")
        click.echo("Run 'mailflow setup-workflows' again to add workflows")
        sys.exit(0)
    except Exception as e:
        click.echo(f"\n✗ Setup failed: {e}", err=True)
        sys.exit(1)

    # Summary
    click.echo(f"\n{'='*60}")
    click.echo(f"✓ Created {created_count} new workflows")
    click.echo(f"  Total workflows: {total_workflows}")
    click.echo(f"\nWorkflows saved to: {config.config_dir / 'workflows.json'}")


@cli.command()
def version():
    """Show mailflow version"""
    from mailflow import __version__

    click.echo(f"mailflow version {__version__}")


if __name__ == "__main__":
    cli()
