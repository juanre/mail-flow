#!/usr/bin/env python

import sys
from pprint import pprint

from pmail.config import Config
from pmail.email_extractor import EmailExtractor
from pmail.models import DataStore
from pmail.similarity import SimilarityEngine
from pmail.ui import WorkflowSelector
from pmail.worklow import Workflows


def process(messg):
    # Initialize components
    config = Config()
    extractor = EmailExtractor()
    data_store = DataStore(config)
    similarity_engine = SimilarityEngine(config)
    ui = WorkflowSelector(config, data_store, similarity_engine)
    
    # Extract email data
    email_data = extractor.extract(messg)
    
    # Let user select workflow
    selected_workflow = ui.select_workflow(email_data)
    
    if selected_workflow:
        print(f"\nApplying workflow: {selected_workflow}")
        
        # Execute the workflow
        workflow_def = data_store.workflows.get(selected_workflow)
        if workflow_def:
            # Get the action function
            if workflow_def.action_type in Workflows:
                action_func = Workflows[workflow_def.action_type]
                # Execute with email data and parameters
                try:
                    action_func(email_data, **workflow_def.action_params)
                    print(f"Workflow '{selected_workflow}' executed successfully!")
                except Exception as e:
                    print(f"Error executing workflow: {e}")
            else:
                print(f"Warning: Action type '{workflow_def.action_type}' not implemented yet.")
    else:
        print("\nNo workflow selected, email skipped.")


def main():
    if len(sys.argv) == 2:
        with open(sys.argv[1]) as message:
            process(message.read())
    else:
        process(sys.stdin.read())


if __name__ == "__main__":
    main()
