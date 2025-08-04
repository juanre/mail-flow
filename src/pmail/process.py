#!/usr/bin/env python

import sys
import logging
from typing import Optional

from pmail.config import Config
from pmail.email_extractor import EmailExtractor
from pmail.models import DataStore
from pmail.similarity import SimilarityEngine
from pmail.ui import WorkflowSelector
from pmail.workflow import Workflows
from pmail.exceptions import PmailError, EmailParsingError, WorkflowError
from pmail.logging_config import setup_logging

logger = logging.getLogger(__name__)


def process(message: str, config: Optional[Config] = None) -> None:
    """
    Process an email message through the pmail workflow.

    Args:
        message: Email message text
        config: Optional configuration object
    """
    try:
        # Initialize components
        if config is None:
            config = Config()

        extractor = EmailExtractor()
        data_store = DataStore(config)
        similarity_engine = SimilarityEngine(config)
        ui = WorkflowSelector(config, data_store, similarity_engine)

        # Extract email data
        logger.debug("Extracting email features")
        email_data = extractor.extract(message)
        logger.info(f"Processing email from {email_data.get('from', 'unknown')}")

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
                        action_func(email_data, **workflow_def.action_params)
                        print(f"\n✓ Workflow '{selected_workflow}' completed!")
                        logger.info(f"Workflow '{selected_workflow}' completed successfully")
                    except WorkflowError as e:
                        print(f"\n✗ Workflow error: {e}")
                        logger.error(f"Workflow execution failed: {e}")
                        sys.exit(2)
                    except Exception as e:
                        print(f"\n✗ Unexpected error: {e}")
                        logger.exception(f"Unexpected error in workflow execution")
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
            with open(sys.argv[1], "r", encoding="utf-8", errors="replace") as message_file:
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
