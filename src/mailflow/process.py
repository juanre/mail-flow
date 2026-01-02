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
from file_classifier import Model, extract_features

logger = logging.getLogger(__name__)


async def process(
    message: str,
    config: Config | None = None,
    llm_model: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    train_only: bool = False,
    replay: bool = False,
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
        train_only: Train classifier and store decisions, but don't execute workflows
        replay: Execute stored decisions without re-asking or re-training
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

                # In replay mode, use the stored decision
                if replay:
                    # Validate workflow still exists
                    if prev_workflow not in data_store.workflows:
                        print(f"\n✗ REPLAY ERROR: Stored workflow '{prev_workflow}' no longer exists")
                        available = ", ".join(sorted(data_store.workflows.keys())[:5])
                        print(f"  Available workflows: {available}...")
                        logger.error(f"Replay mode: workflow '{prev_workflow}' not found")
                        return
                    print(f"\n⊘ REPLAY: Using stored decision '{prev_workflow}' from {prev_date}")
                    logger.info(f"Replay mode: using stored workflow '{prev_workflow}'")
                    selected_workflow = prev_workflow
                    # Skip to execution (don't return, continue below)
                else:
                    print(f"\n⊘ Email already processed:")
                    print(f"  Workflow: {prev_workflow}")
                    print(f"  Date: {prev_date}")
                    print(f"\nUse --force to reprocess")
                    logger.info(f"Email {message_id} already processed, skipping")
                    return
            else:
                selected_workflow = None
        else:
            selected_workflow = None

        # In replay mode with no stored decision, skip this email
        if replay and selected_workflow is None:
            print("\n⊘ REPLAY: No stored decision found, skipping")
            logger.info("Replay mode: no stored decision, skipping")
            return

        # Let user select workflow (unless we already have one from replay)
        if selected_workflow is None:
            selected_workflow = await ui.select_workflow(email_data, skip_training=replay)

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
                        elif train_only:
                            # Train-only mode: store decision but don't execute workflow
                            print(f"(train-only) Storing decision '{selected_workflow}', skipping workflow execution")
                            logger.info(f"train-only: storing decision '{selected_workflow}'")
                            tracker.mark_as_processed(message, message_id, selected_workflow)
                        else:
                            # Normal or replay mode: execute the workflow
                            # Call action based on type
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

                            # Mark as processed (update timestamp even in replay for audit trail)
                            tracker.mark_as_processed(message, message_id, selected_workflow)

                        # Train shared classifier (skip in replay mode to avoid duplicates)
                        if not replay:
                            try:
                                model_path = str(config.state_dir / "classifier.json")
                                model = Model(model_path)
                                feats = extract_features("application/pdf", {  # modality-agnostic baseline
                                    "origin": {
                                        "subject": email_data.get("subject", ""),
                                        "from": email_data.get("from", ""),
                                    }
                                })
                                model.add_example(feats, selected_workflow)
                                model.save()
                            except Exception as e:
                                print(f"\n⚠ Warning: Failed to train shared classifier: {e}")
                                logger.error(f"Failed to train shared classifier: {e}")
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
