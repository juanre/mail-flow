#!/usr/bin/env python
# ABOUTME: Main email processing orchestration for mailflow CLI.
# ABOUTME: Coordinates email extraction, classification, workflow selection, and execution.

import logging
import sys

from mailflow.config import Config
from mailflow.email_extractor import EmailExtractor
from mailflow.exceptions import EmailParsingError, MailflowError, WorkflowError
from mailflow.logging_config import setup_logging
from mailflow.models import DataStore
from mailflow.processed_emails_tracker import ProcessedEmailsTracker
from mailflow.ui import WorkflowSelector
from mailflow.workflow import Workflows

logger = logging.getLogger(__name__)


async def process(
    message: str,
    config: Config | None = None,
    llm_model: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    context: dict | None = None,
    interactive: bool = False,
) -> None:
    """
    Process an email message through the mailflow workflow.

    Args:
        message: Email message text
        config: Optional configuration object
        llm_model: Override config LLM model alias (fast, balanced, deep)
        force: Force reprocessing of already processed emails
        dry_run: Preview mode - don't execute or store anything
        context: Optional extra context to merge into email_data (e.g., _position, _total, _thread_info)
        interactive: If True, prompt user to validate classification; if False, accept automatically
    """
    try:
        # Initialize components
        if config is None:
            config = Config()

        # Initialize processed emails tracker
        tracker = ProcessedEmailsTracker(config)

        # Override LLM model from CLI if provided
        if llm_model is not None:
            config.settings["llm"]["model_alias"] = llm_model

        extractor = EmailExtractor()
        data_store = DataStore(config)

        ui = WorkflowSelector(config, data_store, interactive=interactive)

        # Extract email data
        logger.debug("Extracting email features")
        email_data = extractor.extract(message)

        # Merge optional context (e.g., batch position, thread info)
        if context:
            email_data.update(context)

        message_id = email_data.get("message_id", "")
        logger.info(f"Processing email from {email_data.get('from', 'unknown')}")

        # Check if already processed (unless force)
        if not force and tracker.is_processed(message, message_id):
            processed_info = tracker.get_processed_info(message, message_id)
            if processed_info:
                prev_workflow = processed_info.get("workflow_name", "unknown")
                prev_date = processed_info.get("processed_at", "unknown")
                print(f"\n⊘ Email already processed:")
                print(f"  Workflow: {prev_workflow}")
                print(f"  Date: {prev_date}")
                print(f"\nUse --force to reprocess")
                logger.info(f"Email {message_id} already processed, skipping")
                return

        # Let user select workflow
        selected_workflow = await ui.select_workflow(email_data)

        if selected_workflow:
            print(f"\n{'='*60}")
            print(f"Executing workflow: {selected_workflow}")
            print(f"{'='*60}")

            # Execute the workflow
            workflow_def = data_store.workflows.get(selected_workflow)
            if workflow_def:
                # Get the action function
                if workflow_def.action_type in Workflows:
                    action_func = Workflows[workflow_def.action_type]
                    # Execute with email data and parameters
                    try:
                        logger.info(
                            f"Executing {workflow_def.action_type} for {selected_workflow}"
                        )
                        # Add workflow metadata to email_data for storage
                        email_data["_workflow_name"] = selected_workflow
                        # Get confidence score from rankings if available
                        confidence = 0.0
                        for wf_name, score, _ in email_data.get("_rankings", []):
                            if wf_name == selected_workflow:
                                confidence = score
                                break
                        email_data["_confidence_score"] = confidence

                        if dry_run:
                            print("(dry-run) Skipping action execution and processed marker")
                            logger.info("dry-run: not executing action or marking processed")
                        else:
                            # Execute the workflow
                            if workflow_def.action_type in ["save_attachment", "save_pdf", "save_email_as_pdf"]:
                                # Archive-protocol actions (document storage)
                                action_func(
                                    message=email_data,
                                    workflow=selected_workflow,
                                    config=config,
                                    **workflow_def.action_params
                                )
                            else:
                                # Non-archive actions (e.g., create_todo)
                                action_func(email_data, **workflow_def.action_params)

                            print(f"\n✓ Workflow '{selected_workflow}' completed!")
                            logger.info(f"Workflow '{selected_workflow}' completed successfully")

                            # Mark as processed
                            tracker.mark_as_processed(message, message_id, selected_workflow)
                    except WorkflowError as e:
                        print(f"\n✗ Workflow error: {e}")
                        logger.error(f"Workflow execution failed: {e}")
                        sys.exit(2)
                    except Exception as e:
                        print(f"\n✗ Unexpected error: {e}")
                        logger.exception("Unexpected error in workflow execution")
                        sys.exit(3)
                else:
                    print(f"\n✗ Action type '{workflow_def.action_type}' not implemented.")
                    logger.error(f"Unknown action type: {workflow_def.action_type}")
                    sys.exit(4)
            else:
                print(f"\n✗ Workflow '{selected_workflow}' not found.")
                logger.error(f"Workflow not found: {selected_workflow}")
                sys.exit(5)
        else:
            print("\n✓ No workflow selected, email skipped.")
            logger.info("No workflow selected")

    except EmailParsingError as e:
        print(f"\n✗ Email parsing error: {e}")
        logger.error(f"Failed to parse email: {e}")
        sys.exit(1)
    except MailflowError as e:
        print(f"\n✗ Error: {e}")
        logger.error(f"mailflow error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n✓ Operation cancelled by user.")
        logger.info("Operation cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        logger.exception("Unexpected error in process()")
        sys.exit(1)
