"""pmail command-line interface"""

import logging
import sys
from pathlib import Path

import click

from pmail.config import Config
from pmail.logging_config import setup_logging
from pmail.models import DataStore, WorkflowDefinition
from pmail.process import process as process_email

logger = logging.getLogger(__name__)


@click.group(invoke_without_command=True)
@click.pass_context
@click.option("--debug", is_flag=True, help="Enable debug logging")
def cli(ctx, debug):
    """pmail - Smart Email Processing for Mutt

    When invoked without a subcommand, processes email from stdin.
    """
    # Setup logging
    log_level = "DEBUG" if debug else "INFO"
    setup_logging(log_level)

    # If no subcommand, process email from stdin
    if ctx.invoked_subcommand is None:
        process_stdin()


def process_stdin():
    """Process email from stdin (default behavior for mutt integration)"""
    try:
        email_content = sys.stdin.read()
        if not email_content:
            logger.error("No email content received from stdin")
            sys.exit(1)

        process_email(email_content)
    except KeyboardInterrupt:
        print("\n✗ Cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to process email: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.option("--reset", is_flag=True, help="Reset configuration (backup existing)")
def init(reset):
    """Initialize pmail configuration with default workflows"""
    config_dir = Path.home() / ".pmail"

    # Handle existing configuration
    if config_dir.exists() and reset:
        backup_dir = config_dir.with_suffix(".pmail.backup")
        if backup_dir.exists():
            import shutil

            shutil.rmtree(backup_dir)
        config_dir.rename(backup_dir)
        click.echo(f"✓ Backed up existing configuration to {backup_dir}")
    elif config_dir.exists() and not reset:
        click.echo(f"Configuration already exists at {config_dir}")
        click.echo("Use --reset to backup and create fresh configuration")
        return

    # Initialize configuration
    click.echo("\nInitializing pmail configuration...")
    config = Config()
    data_store = DataStore(config)

    # Create useful default workflows for three entities
    entities = [
        ("gsk", "GreaterSkies"),
        ("tsm", "TheStarMaps"),
        ("jro", "Juan Reyero"),
    ]

    categories = [
        ("expense", "expenses"),
        ("tax-doc", "tax documents"),
        ("doc", "general documents"),
    ]

    default_workflows = []

    # Create workflows for each entity and category
    for entity_code, entity_name in entities:
        for category_code, category_desc in categories:
            workflow = {
                "name": f"{entity_code}-{category_code}",
                "description": f"Save {entity_name} {category_desc}",
                "action_type": "save_pdf",
                "action_params": {
                    "directory": f"~/Documents/pmail/{entity_code}/{category_code}",
                    "filename_template": "{date}-{from}-{subject}",
                },
            }
            default_workflows.append(workflow)

    # Add generic workflow
    default_workflows.append(
        {
            "name": "create-todo",
            "description": "Create a todo item from email",
            "action_type": "create_todo",
            "action_params": {"todo_file": "~/todos.txt"},
        }
    )

    click.echo("\nCreating default workflows...")
    for workflow_data in default_workflows:
        try:
            workflow = WorkflowDefinition(**workflow_data)
            if workflow.name not in data_store.workflows:
                data_store.add_workflow(workflow)
                click.echo(f"  ✓ {workflow.name}: {workflow.description}")
        except Exception as e:
            click.echo(f"  ✗ Failed to create {workflow_data['name']}: {e}", err=True)

    # Create directories
    click.echo("\nCreating workflow directories...")
    directories = []

    # Create directories for each entity and category
    for entity_code, _ in entities:
        for category_code, _ in categories:
            directories.append(f"~/Documents/pmail/{entity_code}/{category_code}")

    for dir_path in directories:
        full_path = Path(dir_path).expanduser()
        try:
            full_path.mkdir(parents=True, exist_ok=True)
            click.echo(f"  ✓ {dir_path}")
        except Exception as e:
            click.echo(f"  ✗ Failed to create {dir_path}: {e}", err=True)

    # Show summary
    click.echo(f"\n✓ Configuration initialized at {config.config_dir}")
    click.echo(f"  Workflows: {len(data_store.workflows)}")
    click.echo(f"  Learning examples: {len(data_store.criteria_instances)}")

    click.echo("\n📝 Add to your .muttrc:")
    click.echo('  macro index,pager \\cp "<pipe-message>pmail<enter>" "Process with pmail"')
    click.echo("\n🚀 Press Ctrl-P in mutt to start processing emails!")


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

    click.echo("\n📊 pmail Statistics\n")
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
    from pmail.metadata_store import MetadataStore

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
        pmail data gsk/expense/2025/2025-07-29-dropbox.com-subscription.pdf
        pmail data 2025-07-29-dropbox.com-subscription.pdf
    """
    import json

    from pmail.metadata_store import MetadataStore

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
    base_dirs.add(Path("~/Documents/pmail").expanduser())
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
def version():
    """Show pmail version"""
    from pmail import __version__

    click.echo(f"pmail version {__version__}")


if __name__ == "__main__":
    cli()
