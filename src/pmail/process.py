#!/usr/bin/env python

import logging
import sys

from pmail.config import Config
from pmail.email_extractor import EmailExtractor
from pmail.exceptions import EmailParsingError, PmailError, WorkflowError
from pmail.hybrid_classifier import HybridClassifier
from pmail.llm_classifier import LLMClassifier
from pmail.logging_config import setup_logging
from pmail.models import DataStore
from pmail.processed_emails_tracker import ProcessedEmailsTracker
from pmail.similarity import SimilarityEngine
from pmail.ui import WorkflowSelector
from pmail.workflow import Workflows

logger = logging.getLogger(__name__)


def process(
    message: str,
    config: Config | None = None,
    llm_enabled: bool | None = None,
    llm_model: str | None = None,
    force: bool = False,
) -> None:
    """
    Process an email message through the pmail workflow.

    Args:
        message: Email message text
        config: Optional configuration object
        llm_enabled: Override config to enable/disable LLM classification
        llm_model: Override config LLM model alias (fast, balanced, deep)
        force: Force reprocessing of already processed emails
    """
    try:
        # Initialize components
        if config is None:
            config = Config()

        # Initialize processed emails tracker
        tracker = ProcessedEmailsTracker(config)

        # Override LLM settings from CLI if provided
        if llm_enabled is not None:
            config.settings["llm"]["enabled"] = llm_enabled
        if llm_model is not None:
            config.settings["llm"]["model_alias"] = llm_model

        extractor = EmailExtractor()
        data_store = DataStore(config)
        similarity_engine = SimilarityEngine(config)

        # Setup hybrid classifier with LLM if enabled
        hybrid_classifier = None
        llm_classifier = None
        if config.settings.get("llm", {}).get("enabled", False):
            try:
                model_alias = config.settings["llm"].get("model_alias", "balanced")
                # Note: LLMClassifier context management is handled in hybrid_classifier.classify()
                # via async context manager which properly manages the LLM service lifecycle
                llm_classifier = LLMClassifier(model_alias=model_alias)
                hybrid_classifier = HybridClassifier(similarity_engine, llm_classifier)
                logger.info(f"LLM classification enabled (model: {model_alias})")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM: {e}, using similarity only")
                hybrid_classifier = None

        ui = WorkflowSelector(config, data_store, similarity_engine, hybrid_classifier)

        # Extract email data
        logger.debug("Extracting email features")
        email_data = extractor.extract(message)
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
        selected_workflow = ui.select_workflow(email_data)

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
    except PmailError as e:
        print(f"\n✗ Error: {e}")
        logger.error(f"pmail error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n✓ Operation cancelled by user.")
        logger.info("Operation cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        logger.exception("Unexpected error in process()")
        sys.exit(1)


def main():
    """Main entry point for pmail"""
    # Set up logging
    log_level = "INFO"  # Could be made configurable
    if "--debug" in sys.argv:
        log_level = "DEBUG"
        sys.argv.remove("--debug")

    setup_logging(log_level=log_level, log_file="pmail.log")

    logger.info("pmail started")

    try:
        if len(sys.argv) == 2:
            # Read email from file
            with open(sys.argv[1], encoding="utf-8", errors="replace") as message_file:
                message_text = message_file.read()
        else:
            # Read email from stdin
            message_text = sys.stdin.read()

        if not message_text:
            print("✗ No email content provided")
            logger.error("No email content provided")
            sys.exit(1)

        process(message_text)

    except FileNotFoundError as e:
        print(f"✗ File not found: {sys.argv[1]}")
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except PermissionError as e:
        print(f"✗ Permission denied: {sys.argv[1]}")
        logger.error(f"Permission denied: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Failed to read email: {e}")
        logger.exception("Failed to read email")
        sys.exit(1)
    finally:
        logger.info("pmail finished")


if __name__ == "__main__":
    main()
