# ABOUTME: Command-line interface for mailflow email processing workflows
# ABOUTME: Provides commands for processing, searching, stats, and Gmail integration
"""mailflow command-line interface"""

import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from mailflow.config import Config
from mailflow.commands.index_search import register as register_index_commands
from mailflow.commands.gmail_batch_workflows import register as register_gmail_batch
from mailflow.logging_config import setup_logging
from mailflow.models import DataStore, WorkflowDefinition, WORKFLOWS_SCHEMA_VERSION
from mailflow.process import process as process_email

logger = logging.getLogger(__name__)

def _write_empty_workflows(workflows_file: Path) -> None:
    workflows_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": WORKFLOWS_SCHEMA_VERSION, "workflows": []}
    workflows_file.write_text(json.dumps(payload, indent=2) + "\n")


@click.group(invoke_without_command=True)
@click.pass_context
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.option("--llm-model", default=None, help="LLM model alias: fast, balanced, or deep")
@click.option("--force", is_flag=True, help="Reprocess already processed emails")
@click.option("--interactive", is_flag=True, help="Interactive mode: prompt user to validate classification")
def cli(ctx, debug, llm_model, force, interactive):
    """mailflow - Smart Email Processing for Mutt

    When invoked without a subcommand, processes email from stdin.

    By default, mailflow runs in non-interactive mode: decisions from
    llm-archivist are accepted automatically. Use --interactive to
    prompt for confirmation/correction.
    """
    # Load environment from .env if present (for archivist/LLM/DB config)
    load_dotenv()

    # Store options in context for process_stdin to use
    ctx.ensure_object(dict)
    ctx.obj["llm_model"] = llm_model
    ctx.obj["force"] = force
    ctx.obj["interactive"] = interactive

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
        llm_model = ctx.obj.get("llm_model")
        force = ctx.obj.get("force", False)
        interactive = ctx.obj.get("interactive", False)

        asyncio.run(
            process_email(email_content, llm_model=llm_model, force=force, interactive=interactive)
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


def _interactive_workflow_setup(config: Config, data_store: DataStore) -> tuple[int, int]:
    """Shared interactive workflow setup logic.

    Prompts user for entities and document types, creates workflows.

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
        click.echo(f"\n⚠️  This will create {workflow_count} workflows.")
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
                kind="document",
                criteria={"summary": f"{entity_name} {doc_desc}"},
                handling={
                    "archive": {
                        "target": "document",
                        "entity": entity_code,
                        "doctype": doc_code,
                    },
                    "index": {"llmemory": True},
                },
            )

            try:
                if workflow.name not in data_store.workflows:
                    data_store.add_workflow(workflow)
                    click.echo(f"  ✓ {workflow_name}: {workflow.criteria['summary']}")
                    created_count += 1
                else:
                    click.echo(f"  ⊘ {workflow_name}: Already exists")
            except Exception as e:
                click.echo(f"  ✗ {workflow_name}: Failed - {e}", err=True)

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

    workflows_file = config.get_workflows_file()

    # Handle existing configuration
    if workflows_file.exists() and reset:
        backup_path = config.backup_file(workflows_file)
        click.echo(f"✓ Backed up existing workflows to {backup_path}")
        _write_empty_workflows(workflows_file)
    elif workflows_file.exists() and not reset:
        click.echo(f"Configuration already exists at {config.config_dir}")
        click.echo("Use --reset to backup and create fresh configuration")
        return
    else:
        _write_empty_workflows(workflows_file)

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
    click.echo("\n  3. Configure docflow:")
    click.echo("     - Ensure ~/.config/docflow/config.toml has [archivist] database_url/db_schema")
    click.echo("     - Set ANTHROPIC_API_KEY=sk-ant-...")
    click.echo(f"\n💡 Tip: Run 'mailflow setup-workflows' anytime to add more workflows")


@cli.command()
def stats():
    """Show mailflow statistics"""
    import asyncio
    config = Config()
    data_store = DataStore(config)

    click.echo("\n📊 mailflow Statistics\n")
    click.echo(f"Total workflows: {len(data_store.workflows)}")

    if data_store.workflows:
        click.echo("\nConfigured workflows:")
        for name, wf in sorted(data_store.workflows.items()):
            click.echo(f"  {name}: {wf.kind} ({wf.archive_entity}/{wf.archive_doctype})")

    # Get learning metrics from llm-archivist
    try:
        from mailflow.archivist_client import get_metrics, set_config
        set_config(config)
        metrics = asyncio.run(get_metrics())
        if metrics:
            click.echo("\nClassifier metrics (llm-archivist):")
            click.echo(f"  Total decisions: {metrics.get('total_decisions', 0)}")
            click.echo(f"  Feedback count: {metrics.get('feedback_count', 0)}")
    except Exception as e:
        click.echo(f"\n(Classifier metrics unavailable: {e})")


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
    workflows_file = config.get_workflows_file()
    if not workflows_file.exists():
        _write_empty_workflows(workflows_file)
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
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
def reset_training(yes):
    """Reset all training data for a fresh training run.

    Clears:
    - processed_emails.db (email tracking database)
    - PostgreSQL tables: decisions, embeddings, feedback (llm-archivist)

    Use this before re-training to ensure clean, unpolluted data.
    """
    config = Config()

    if not yes:
        click.echo("\n⚠️  This will delete ALL training data:")
        click.echo(f"  - {config.config_dir / 'processed_emails.db'}")
        click.echo("  - PostgreSQL: decisions, embeddings, feedback tables")
        if not click.confirm("\nContinue?", default=False):
            click.echo("Cancelled.")
            return

    click.echo("\nResetting training data...")

    # 2. Delete processed_emails.db
    processed_db = config.config_dir / "processed_emails.db"
    if processed_db.exists():
        processed_db.unlink()
        click.echo(f"  ✓ Deleted {processed_db}")
    else:
        click.echo(f"  - {processed_db} (not found)")

    # 3. Truncate PostgreSQL tables
    try:
        db_url = config.get_archivist_database_url()
        schema = config.get_archivist_db_schema()
    except ConfigurationError as e:
        click.echo(f"  ⚠ {e}")
        db_url = None
        schema = None

    if db_url and schema:
        try:

            async def _truncate_tables():
                from pgdbm import AsyncDatabaseManager, DatabaseConfig

                cfg = DatabaseConfig(connection_string=db_url, schema=schema)
                db = AsyncDatabaseManager(cfg)
                await db.connect()
                try:
                    await db.execute(
                        f"TRUNCATE {schema}.embeddings, {schema}.feedback, "
                        f"{schema}.decisions RESTART IDENTITY CASCADE"
                    )
                finally:
                    await db.disconnect()

            asyncio.run(_truncate_tables())
            click.echo(f"  ✓ Truncated PostgreSQL tables in schema '{schema}'")
        except Exception as e:
            click.echo(f"  ✗ PostgreSQL error: {e}", err=True)
    else:
        click.echo("  ⚠ Skipping PostgreSQL tables (archivist config missing)")

    click.echo("\n✓ Training data reset complete.")
    click.echo("  Run 'mailflow batch ... --train-only' to retrain.")


@cli.command()
def version():
    """Show mailflow version"""
    from mailflow import __version__

    click.echo(f"mailflow version {__version__}")


if __name__ == "__main__":
    cli()
