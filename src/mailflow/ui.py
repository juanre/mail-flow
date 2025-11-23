# ABOUTME: Interactive UI for workflow selection and creation in mailflow.
# ABOUTME: Handles user interaction for classifying and processing emails with workflows.
import asyncio
import logging
from datetime import datetime

from mailflow.linein import LineInput
from mailflow.models import CriteriaInstance, WorkflowDefinition

logger = logging.getLogger(__name__)


class WorkflowSelector:
    """Interactive UI for selecting workflows"""

    def __init__(self, config, data_store, similarity_engine, hybrid_classifier=None):
        self.config = config
        self.data_store = data_store
        self.similarity_engine = similarity_engine
        self.hybrid_classifier = hybrid_classifier
        self.max_suggestions = config.settings["ui"]["max_suggestions"]
        self.show_confidence = config.settings["ui"]["show_confidence"]

    def select_workflow(self, email_data: dict) -> str | None:
        """Present workflow options and get user selection"""

        # Get ranked workflows (use llm-archivist if enabled, else hybrid/similarity)
        criteria_instances = self.data_store.get_recent_criteria()
        rankings = []
        llm_suggestion = None

        # Prefer external classifier when enabled
        arch_result = None
        if self.config.settings.get("classifier", {}).get("enabled"):
            try:
                from mailflow.archivist_integration import classify_with_archivist

                arch = classify_with_archivist(
                    email_data,
                    self.data_store,
                    interactive=True,
                    allow_llm=self.config.settings.get("llm", {}).get("enabled", False),
                    max_candidates=self.max_suggestions,
                )
                arch_result = arch
                rankings = arch.get("rankings") or []
                # Treat top candidate as suggestion
                if rankings:
                    top_label, top_score, _ = rankings[0]
                    class _Tmp:  # minimal shim to match existing usage structure
                        def __init__(self, workflow, confidence, reasoning=""):
                            self.workflow = workflow
                            self.confidence = confidence
                            self.reasoning = reasoning

                    llm_suggestion = _Tmp(top_label, float(top_score))
            except Exception as e:
                logger.warning(f"archivist classify failed: {e}; falling back")

        if not rankings and self.hybrid_classifier:
            try:
                # Note: hybrid_classifier.classify() manages async context internally
                result = asyncio.run(
                    self.hybrid_classifier.classify(
                        email_data, self.data_store.workflows, criteria_instances
                    )
                )
                rankings = result["rankings"]
                llm_suggestion = result.get("llm_suggestion")
            except Exception as e:
                logger.warning(f"Hybrid classification failed: {e}, falling back to similarity")
        if not rankings:
            rankings = self.similarity_engine.rank_workflows(
                email_data["features"], criteria_instances, self.max_suggestions
            )
            llm_suggestion = llm_suggestion  # keep any previous suggestion

        # Store rankings in email_data for later use
        email_data["_rankings"] = rankings

        # Display email info
        print("\n" + "=" * 60)
        print(f"From: {email_data['from']}")
        print(f"Subject: {email_data['subject']}")
        if email_data["attachments"]:
            print(f"Attachments: {len(email_data['attachments'])} files")
            for att in email_data["attachments"][:3]:
                print(f"  - {att['filename']}")
        print("=" * 60 + "\n")

        # Display LLM suggestion if available and confident
        if llm_suggestion and llm_suggestion.confidence > 0.7:
            print("\n🤖 AI Suggestion:")
            print(f"  → {llm_suggestion.workflow} ({llm_suggestion.confidence:.0%} confidence)")
            print(f"     {llm_suggestion.reasoning}")
            print()

        # Build options list - include all workflow names for tab completion
        options = ["skip", "new"]
        option_map = {"skip": None, "new": "new"}

        # Add all workflow names to options for tab completion
        for wf_name in self.data_store.workflows:
            options.append(wf_name)
            option_map[wf_name] = wf_name

        if rankings:
            print("Suggested workflows (based on similarity):")
            for i, (workflow_name, score, instances) in enumerate(rankings, 1):
                workflow = self.data_store.workflows.get(workflow_name)
                if workflow:
                    option_key = str(i)
                    options.append(option_key)
                    option_map[option_key] = workflow_name

                    # Display option
                    confidence = f" ({score:.0%})" if self.show_confidence else ""
                    print(f"  {i}. {workflow.description}{confidence}")

                    # Show why it matched
                    if instances and score > 0.3:
                        best_instance = instances[0]
                        explanations = self.similarity_engine.get_feature_explanation(
                            email_data["features"], best_instance
                        )
                        if explanations:
                            print(f"     Matches because: {', '.join(explanations.values())}")
        else:
            print("No similar workflows found in history.\n")

        print("\nOptions:")
        print("  Enter number (1-9) to select a suggested workflow")
        print("  Type workflow name (with tab completion)")
        print("  'skip' to skip this email")
        print("  'new' to create a new workflow")

        # Get user input
        if rankings and rankings[0][1] > 0.7:
            # High confidence match, suggest as default
            default = "1"
            prompt_text = f"Selection [default: {default}]"
        else:
            default = None
            prompt_text = "Selection"

        selector = LineInput(prompt_text, typical=options, only_typical=False, with_history=True)

        choice = selector.ask(default=default)

        selected_workflow = option_map.get(choice)

        if selected_workflow == "new":
            # Create new workflow
            selected_workflow = self._create_new_workflow()

        if selected_workflow:
            # Record the decision
            instance = CriteriaInstance(
                email_id=email_data["message_id"],
                workflow_name=selected_workflow,
                timestamp=datetime.now(),
                email_features=email_data["features"],
                user_confirmed=True,
                confidence_score=(
                    rankings[0][1] if rankings and rankings[0][0] == selected_workflow else 0.0
                ),
            )
            self.data_store.add_criteria_instance(instance)

            # Send feedback to external classifier if available
            try:
                if arch_result and arch_result.get("decision_id"):
                    from mailflow.archivist_integration import record_feedback
                    record_feedback(int(arch_result["decision_id"]), selected_workflow, "confirmed")
            except Exception as e:
                logger.debug(f"archivist feedback not recorded: {e}")

        return selected_workflow

    def _create_new_workflow(self) -> str | None:
        """Interactive workflow creation"""
        print("\n--- Create New Workflow ---")

        name_input = LineInput("Workflow name", with_history=True)
        name = name_input.ask()

        if not name:
            return None

        desc_input = LineInput("Description", with_history=False)
        description = desc_input.ask()

        # Check if user wants to use a template
        use_template = LineInput("Use a workflow template?", typical=["no", "yes"])
        if use_template.ask(default="no") == "yes":
            from mailflow.workflow_templates import WORKFLOW_TEMPLATES

            print("\nAvailable templates:")
            for key, template in WORKFLOW_TEMPLATES.items():
                print(f"  - {key}: {template['description']}")

            template_input = LineInput("Template name", typical=list(WORKFLOW_TEMPLATES.keys()))
            template_key = template_input.ask()

            if template_key in WORKFLOW_TEMPLATES:
                template = WORKFLOW_TEMPLATES[template_key]
                name = template["name"]
                description = template["description"]
                action_type = template["action_type"]
                action_params = template["action_params"].copy()
                print(f"\n✓ Using template: {description}")
            else:
                print("Template not found, creating custom workflow...")
                action_types = [
                    "save_attachment",
                    "save_email_as_pdf",
                    "save_pdf",
                    "create_todo",
                ]
                action_input = LineInput("Action type", typical=action_types, only_typical=True)
                action_type = action_input.ask()
                action_params = {}
        else:
            action_types = [
                "save_attachment",
                "save_email_as_pdf",
                "save_pdf",
                "create_todo",
            ]
            action_input = LineInput("Action type", typical=action_types, only_typical=True)
            action_type = action_input.ask()
            action_params = {}

        # Configure action parameters if not using template
        if action_type == "save_attachment" and not action_params:
            dir_input = LineInput(
                "Directory",
                typical=[
                    "~/Documents/mailflow/jro/expense",
                    "~/Documents/mailflow/tsm/expense",
                    "~/Documents/mailflow/gsk/expense",
                    "~/Documents/mailflow/jro/invoice",
                    "~/receipts",
                ],
            )
            action_params["directory"] = dir_input.ask()
            pattern_input = LineInput("File pattern", typical=["*.pdf", "*.*", "*.jpg", "*.png"])
            action_params["pattern"] = pattern_input.ask(default="*.*")

        elif action_type == "save_email_as_pdf" and not action_params:
            dir_input = LineInput(
                "Directory",
                typical=[
                    "~/Documents/mailflow/jro/doc",
                    "~/Documents/mailflow/tsm/doc",
                    "~/Documents/mailflow/gsk/doc",
                    "~/invoices",
                ],
            )
            action_params["directory"] = dir_input.ask(default="~/receipts")
            template_input = LineInput(
                "Filename template", typical=["{date}_{from}_{subject}.pdf"]
            )
            action_params["filename_template"] = template_input.ask(
                default="{date}_{from}_{subject}.pdf"
            )

        elif action_type == "save_pdf" and not action_params:
            dir_input = LineInput(
                "Directory",
                typical=[
                    "~/Documents/mailflow/jro/expense",
                    "~/Documents/mailflow/tsm/expense",
                    "~/Documents/mailflow/gsk/expense",
                    "~/Documents/mailflow/jro/invoice",
                    "~/Documents/mailflow/tsm/invoice",
                    "~/receipts",
                ],
            )
            action_params["directory"] = dir_input.ask()
            template_input = LineInput(
                "Filename template (for emails without PDF)",
                typical=["{date}_{from}_{subject}"],
            )
            action_params["filename_template"] = template_input.ask(
                default="{date}_{from}_{subject}"
            )

        elif action_type == "create_todo" and not action_params:
            file_input = LineInput("Todo file", typical=["~/todos.txt"])
            action_params["todo_file"] = file_input.ask(default="~/todos.txt")

        # Create and save the workflow
        workflow = WorkflowDefinition(
            name=name,
            description=description,
            action_type=action_type,
            action_params=action_params,
        )

        self.data_store.add_workflow(workflow)
        print(f"\nWorkflow '{name}' created successfully!")

        return name
