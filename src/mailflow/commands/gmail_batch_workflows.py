from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
import click

from mailflow.config import Config
from mailflow.gmail_api import poll_and_process as gmail_poll
from mailflow.models import DataStore
from mailflow.process import process as process_email
from mailflow.processed_emails_tracker import ProcessedEmailsTracker
from mailflow.thread_detector import detect_threads, get_thread_info


def _parse_email_date(date_str: str) -> datetime:
    """Parse email Date header into datetime. Returns epoch (UTC) for unparseable dates.

    Always returns timezone-aware datetime (UTC) to ensure consistent comparison.
    """
    from datetime import timezone
    if not date_str:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        dt = parsedate_to_datetime(date_str)
        # Ensure timezone-aware (some dates may be naive)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _discover_email_files(base: Path) -> list[Path]:
    """Discover email files under a directory.

    Supports:
    - Flat or recursive .eml collections
    - Maildir roots or subfolders (cur/new under any subdir)
    """
    base = base.expanduser()
    files: list[Path] = []
    # 1) Plain .eml anywhere under base
    files = list(base.glob("**/*.eml"))
    if files:
        return sorted(files)

    # 2) Maildir: collect files under */cur and */new
    cur_dirs = list(base.glob("**/cur")) + list(base.glob("**/new"))
    seen = set()
    for d in cur_dirs:
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.is_file() and not f.name.startswith("."):
                files.append(f)
                seen.add(f)
    return sorted(files)


def register(cli):
    # New: grouped aliases `mailflow fetch gmail` and `mailflow fetch files`
    @cli.group(name="fetch")
    def fetch():
        """Fetch and process emails from different sources."""
        pass

    @cli.command()
    @click.option("--query", "query", default="", help="Gmail search query (e.g., label:INBOX)")
    @click.option("--label", "label", default=None, help="Only process messages with this Gmail label")
    @click.option("--processed-label", default="mailflow/processed", help="Label to add after processing")
    @click.option("--max-results", default=20, help="Maximum Gmail messages to process per run")
    @click.option("--remove-from-inbox", is_flag=True, help="Remove from INBOX after processing")
    def gmail(query, label, processed_label, max_results, remove_from_inbox):
        """Process emails directly from Gmail via the Gmail API."""
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
            click.echo(f"Processed {count} Gmail message(s)")
        except RuntimeError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)
        except Exception as e:
            click.echo(f"Error: {e}", err=True)
            raise SystemExit(1)

    # Alias: mailflow fetch gmail
    @fetch.command(name="gmail")
    @click.option("--query", "query", default="", help="Gmail search query (e.g., label:INBOX)")
    @click.option("--label", "label", default=None, help="Only process messages with this Gmail label")
    @click.option("--processed-label", default="mailflow/processed", help="Label to add after processing")
    @click.option("--max-results", default=20, help="Maximum Gmail messages to process per run")
    @click.option("--remove-from-inbox", is_flag=True, help="Remove from INBOX after processing")
    def fetch_gmail(query, label, processed_label, max_results, remove_from_inbox):
        """Same as `mailflow gmail`"""
        return gmail.callback(query, label, processed_label, max_results, remove_from_inbox)  # type: ignore[attr-defined]

    @cli.command()
    @click.argument("directory", type=click.Path(exists=True))
    @click.option("--llm-model", default=None, help="LLM model: fast, balanced, or deep")
    @click.option("--auto-threshold", default=0.85, type=float, help="Auto-process above this confidence")
    @click.option("--dry-run", is_flag=True, help="Preview without executing workflows")
    @click.option("--train-only", is_flag=True, help="Train classifier and store decisions, but don't execute workflows")
    @click.option("--replay", is_flag=True, help="Execute stored decisions without re-asking or re-training")
    @click.option("--max-emails", default=None, type=int, help="Limit number of emails to process")
    @click.option("--force", is_flag=True, help="Reprocess already processed emails")
    @click.option("--after", default=None, help="Only emails after this date (YYYY-MM-DD)")
    @click.option("--before", default=None, help="Only emails before this date (YYYY-MM-DD)")
    @click.option("--workflows", "-w", default=None, help="Only classify against these workflows (comma-separated)")
    @click.option("--min-confidence", default=None, type=float, help="Skip emails below this confidence (default 0.45 when --workflows set)")
    @click.option("--similarity-threshold", default=None, type=float, help="Override similarity gate threshold (default 0.5)")
    @click.option("--trust-llm", default=None, type=click.FloatRange(0.0, 1.0), help="Trust LLM judgment without user confirmation. Value is confidence threshold (e.g., 0.8). Accepts above threshold, skips below.")
    def batch(directory, llm_model, auto_threshold, dry_run, train_only, replay, max_emails, force, after, before, workflows, min_confidence, similarity_threshold, trust_llm):
        """Process multiple emails from a directory (.eml files)."""
        asyncio.run(
            _batch_async(directory, llm_model, auto_threshold, dry_run, train_only, replay, max_emails, force, after, before, workflows, min_confidence, similarity_threshold, trust_llm)
        )

    async def _batch_async(directory, llm_model, auto_threshold, dry_run, train_only, replay, max_emails, force, after=None, before=None, workflows=None, min_confidence=None, similarity_threshold=None, trust_llm=None):
        """Async implementation of batch email processing."""
        from mailflow.email_extractor import EmailExtractor
        from mailflow.similarity import SimilarityEngine

        # Validate mutually exclusive flags
        mode_flags = sum([dry_run, train_only, replay])
        if mode_flags > 1:
            click.echo("Error: --dry-run, --train-only, and --replay are mutually exclusive", err=True)
            raise SystemExit(1)

        # --trust-llm sets both auto_threshold and min_confidence to the same value
        # This means: accept if LLM confidence >= threshold, skip if below
        if trust_llm is not None:
            auto_threshold = trust_llm
            min_confidence = trust_llm
            click.echo(f"Trust LLM mode: accepting >= {trust_llm}, skipping below")

        if replay and force:
            click.echo("Error: --replay and --force are mutually exclusive (replay uses stored decisions)", err=True)
            raise SystemExit(1)

        # Parse workflow filter
        workflow_filter = None
        if workflows:
            workflow_filter = [w.strip() for w in workflows.split(",") if w.strip()]
            if min_confidence is None:
                min_confidence = 0.45  # Default when --workflows is specified

        config = Config()

        if llm_model is not None:
            config.settings["llm"]["model_alias"] = llm_model

        data_store = DataStore(config)
        extractor = EmailExtractor()
        similarity_engine = SimilarityEngine(config)
        tracker = ProcessedEmailsTracker(config)

        # Validate workflow filter
        if workflow_filter:
            valid_workflows = set(data_store.workflows.keys())
            invalid = [w for w in workflow_filter if w not in valid_workflows]
            if invalid:
                click.echo(f"Error: Unknown workflows: {', '.join(invalid)}", err=True)
                click.echo(f"Available: {', '.join(sorted(valid_workflows)[:10])}...")
                raise SystemExit(1)
            click.echo(f"Focused training: {', '.join(workflow_filter)} (min confidence: {min_confidence})")

        directory_path = Path(directory).expanduser()
        email_files = _discover_email_files(directory_path)
        if max_emails:
            email_files = email_files[:max_emails]
        if not email_files:
            click.echo(f"No .eml files found in {directory}")
            return

        click.echo(f"Found {len(email_files)} emails to process")

        # Cost warning for LLM classification (archivist uses LLM for all classifications)
        if not dry_run and not train_only:
            estimated_llm_calls = len(email_files) * 0.2
            estimated_cost = estimated_llm_calls * 0.003
            click.echo(f"Estimated LLM cost: ${estimated_cost:.2f} (assumes ~20% need LLM assist)")
            if not click.confirm("Continue with processing?", default=True):
                click.echo("Cancelled by user")
                return

        if dry_run:
            click.echo("DRY RUN MODE - no workflows will be executed")
        elif train_only:
            click.echo("TRAIN-ONLY MODE - decisions will be stored and classifier trained, but workflows won't execute")
        elif replay:
            click.echo("REPLAY MODE - executing stored decisions without re-asking or re-training")

        # Pre-extract all emails to detect threads
        click.echo("Analyzing email threads...")
        email_contents = []
        email_data_list = []
        for email_file in email_files:
            try:
                with open(email_file, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                email_contents.append(content)
                email_data_list.append(extractor.extract(content))
            except Exception:
                email_contents.append("")
                email_data_list.append({})

        # Sort by date descending (most recent first)
        combined = list(zip(email_files, email_contents, email_data_list))
        combined.sort(key=lambda x: _parse_email_date(x[2].get("date", "")), reverse=True)
        email_files, email_contents, email_data_list = (
            [x[0] for x in combined],
            [x[1] for x in combined],
            [x[2] for x in combined],
        )

        # Filter by date range
        if after or before:
            after_dt = datetime.strptime(after, "%Y-%m-%d") if after else None
            before_dt = datetime.strptime(before, "%Y-%m-%d") if before else None
            filtered = []
            for f, c, d in zip(email_files, email_contents, email_data_list):
                email_dt = _parse_email_date(d.get("date", ""))
                if after_dt and email_dt.replace(tzinfo=None) < after_dt:
                    continue
                if before_dt and email_dt.replace(tzinfo=None) > before_dt:
                    continue
                filtered.append((f, c, d))
            original_count = len(email_files)
            email_files, email_contents, email_data_list = (
                [x[0] for x in filtered],
                [x[1] for x in filtered],
                [x[2] for x in filtered],
            )
            click.echo(f"Date filter: {len(email_files)} of {original_count} emails in range")

        # Detect threads
        threads = detect_threads(email_data_list)

        stats = {"processed": 0, "auto": 0, "skipped": 0, "errors": 0}
        total = len(email_files)

        for i, (email_file, email_content, email_data) in enumerate(
            zip(email_files, email_contents, email_data_list), 1
        ):
            try:
                if not email_content:
                    stats["errors"] += 1
                    continue

                message_id = email_data.get("message_id")

                if not force and tracker.is_processed(email_content, message_id):
                    processed_info = tracker.get_processed_info(email_content, message_id)
                    prev_workflow = (
                        processed_info.get("workflow_name", "unknown") if processed_info else "unknown"
                    )
                    click.echo(f"[{i}/{total}] SKIP {email_file.name}: Already processed ({prev_workflow})")
                    stats["skipped"] += 1
                    continue

                # Build context with position, thread info, and workflow filter
                context = {
                    "_position": i,
                    "_total": total,
                    "_thread_info": get_thread_info(email_data, threads),
                    "_workflow_filter": workflow_filter,
                    "_min_confidence": min_confidence,
                    "_auto_threshold": auto_threshold,
                    "_similarity_threshold": similarity_threshold,
                }

                # Process one email through standard pipeline (interactive selection)
                await process_email(
                    email_content,
                    config=config,
                    force=force,
                    dry_run=dry_run,
                    train_only=train_only,
                    replay=replay,
                    context=context
                )
                stats["processed"] += 1
            except Exception as e:
                click.echo(f"[{i}/{total}] ERROR {email_file.name}: {e}", err=True)
                stats["errors"] += 1

        click.echo("\nSummary:")
        click.echo(f"  Processed: {stats['processed']}")
        click.echo(f"  Already processed (skipped): {stats['skipped']}")
        click.echo(f"  Errors: {stats['errors']}")
        if dry_run:
            click.echo("DRY RUN - No workflows were executed")
        elif train_only:
            click.echo("TRAIN-ONLY - Decisions stored and classifier trained, no workflows executed")
        elif replay:
            click.echo("REPLAY - Stored decisions executed without re-training")

    # Alias: mailflow fetch files
    @fetch.command(name="files")
    @click.argument("directory", type=click.Path(exists=True))
    @click.option("--llm-model", default=None, help="LLM model: fast, balanced, or deep")
    @click.option("--auto-threshold", default=0.85, type=float, help="Auto-process above this confidence")
    @click.option("--dry-run", is_flag=True, help="Preview without executing workflows")
    @click.option("--train-only", is_flag=True, help="Train classifier and store decisions, but don't execute workflows")
    @click.option("--replay", is_flag=True, help="Execute stored decisions without re-asking or re-training")
    @click.option("--max-emails", default=None, type=int, help="Limit number of emails to process")
    @click.option("--force", is_flag=True, help="Reprocess already processed emails")
    @click.option("--after", default=None, help="Only emails after this date (YYYY-MM-DD)")
    @click.option("--before", default=None, help="Only emails before this date (YYYY-MM-DD)")
    @click.option("--workflows", "-w", default=None, help="Only classify against these workflows (comma-separated)")
    @click.option("--min-confidence", default=None, type=float, help="Skip emails below this confidence (default 0.45 when --workflows set)")
    @click.option("--similarity-threshold", default=None, type=float, help="Override similarity gate threshold (default 0.5)")
    @click.option("--trust-llm", default=None, type=click.FloatRange(0.0, 1.0), help="Trust LLM judgment without user confirmation. Value is confidence threshold (e.g., 0.8). Accepts above threshold, skips below.")
    def fetch_files(directory, llm_model, auto_threshold, dry_run, train_only, replay, max_emails, force, after, before, workflows, min_confidence, similarity_threshold, trust_llm):
        """Same as `mailflow batch`"""
        return batch.callback(directory, llm_model, auto_threshold, dry_run, train_only, replay, max_emails, force, after, before, workflows, min_confidence, similarity_threshold, trust_llm)  # type: ignore[attr-defined]

    @cli.command()
    @click.option("--limit", "-n", default=10, help="Number of workflows to show")
    def workflows(limit):
        """List available workflows."""
        from mailflow.models import DataStore

        config = Config()
        data_store = DataStore(config)

        click.echo(f"Available workflows ({len(data_store.workflows)} total):")
        shown = 0
        for name, workflow in data_store.workflows.items():
            if shown >= limit:
                remaining = len(data_store.workflows) - limit
                click.echo(f"... and {remaining} more")
                break
            click.echo(f"{name}:")
            click.echo(f"  {workflow.description}")
            click.echo(f"  Type: {workflow.action_type}")
            params = workflow.action_params
            if "directory" in params:
                click.echo(f"  Directory: {params['directory']}")
            if "pattern" in params:
                click.echo(f"  Pattern: {params['pattern']}")
            if "filename_template" in params:
                click.echo(f"  Filename: {params['filename_template']}")
            click.echo("")
