"""pmail command-line interface"""

import sys
import logging
from pathlib import Path
from typing import Optional

import click

from pmail.config import Config
from pmail.models import DataStore, WorkflowDefinition
from pmail.process import process as process_email
from pmail.logging_config import setup_logging

logger = logging.getLogger(__name__)


@click.group(invoke_without_command=True)
@click.pass_context
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.option("--workflow", "-w", help="Specify workflow name (for non-interactive use)")
def cli(ctx, debug, workflow):
    """pmail - Smart Email Processing for Mutt

    When invoked without a subcommand, processes email from stdin.
    """
    # Setup logging
    log_level = "DEBUG" if debug else "INFO"
    setup_logging(log_level)

    # Store workflow in context for subcommands
    ctx.obj = {"workflow": workflow}

    # If no subcommand, process email from stdin
    if ctx.invoked_subcommand is None:
        process_stdin(workflow)


def process_stdin(workflow_name=None):
    """Process email from stdin (default behavior for mutt integration)"""
    try:
        email_content = sys.stdin.read()
        if not email_content:
            logger.error("No email content received from stdin")
            sys.exit(1)

        # Set workflow in environment if specified via CLI
        if workflow_name:
            import os

            os.environ["PMAIL_WORKFLOW"] = workflow_name

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
                    "filename_template": "{date}_{from}_{subject}",
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
            # Show recent PDFs
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
def version():
    """Show pmail version"""
    from pmail import __version__

    click.echo(f"pmail version {__version__}")


if __name__ == "__main__":
    cli()
