# ABOUTME: Interactive UI for workflow selection and creation in mailflow.
# ABOUTME: Handles user interaction for classifying and processing emails with workflows.
import logging

from rich.console import Console
from rich.panel import Panel

from mailflow.linein import LineInput
from mailflow.models import WorkflowDefinition
from mailflow.tui import display_email, format_workflow_choices, get_workflow_prompt

logger = logging.getLogger(__name__)


class WorkflowSelector:
    """UI for selecting workflows (interactive or non-interactive)"""

    def __init__(self, config, data_store, interactive: bool = False):
        self.config = config
        self.data_store = data_store
        self.interactive = interactive
        self.max_suggestions = config.settings["ui"]["max_suggestions"]
        self.show_confidence = config.settings["ui"]["show_confidence"]

    async def select_workflow(self, email_data: dict) -> str | None:
        """Select workflow using llm-archivist classification.

        In non-interactive mode (default): accept llm-archivist decision automatically.
        In interactive mode: prompt user to validate/correct the classification.

        Args:
            email_data: Extracted email data

        Returns:
            Selected workflow name, or None if skipped/null
        """
        console = Console()

        # Extract workflow filter and context from email_data
        workflow_filter = email_data.get("_workflow_filter")
        position = email_data.get("_position", 1)
        total = email_data.get("_total", 1)

        # Classify via llm-archivist (vector KNN + LLM arbiter)
        from mailflow.archivist_integration import classify_with_archivist

        arch_result = await classify_with_archivist(
            email_data,
            self.data_store,
            interactive=self.interactive,
            allow_llm=True,
            max_candidates=self.max_suggestions,
            workflow_filter=workflow_filter,
        )
        rankings = arch_result.get("rankings") or []
        decision_label = arch_result.get("label")
        decision_confidence = float(arch_result.get("confidence", 0.0) or 0.0)

        # Filter rankings to only include existing workflows (and workflow filter if specified)
        valid_workflows = set(self.data_store.workflows.keys())
        if workflow_filter:
            valid_workflows = valid_workflows & set(workflow_filter)
        rankings = [r for r in rankings if r[0] in valid_workflows]

        # Store rankings in email_data for later use
        email_data["_rankings"] = rankings

        # Determine suggestion and confidence.
        # Prefer the classifier's chosen label. Rankings are only supplemental
        # (e.g., vector neighbors/candidates) and may be empty in LLM-only decisions.
        suggestion = None
        if decision_label in valid_workflows:
            suggestion = decision_label

        confidence = decision_confidence if suggestion else 0.0

        # Non-interactive mode: accept llm-archivist decision automatically
        if not self.interactive:
            if suggestion:
                logger.info(f"[{position}/{total}] Non-interactive: accepting {suggestion} ({confidence:.2f})")
            else:
                # No suggestion (null) - skip
                logger.info(f"[{position}/{total}] Non-interactive: no suggestion, skipping")
                return None

            # Return the suggestion without prompting
            return suggestion

        # Interactive mode: prompt user to validate classification
        # Get thread info if available
        thread_info = email_data.get("_thread_info")

        # Display email using rich TUI
        display_email(console, email_data, position, total, thread_info)

        # Show classification result with evidence
        self._display_classification_evidence(console, arch_result, suggestion, confidence)

        # Show workflow choices (filtered if specified)
        workflows_to_show = self.data_store.workflows
        if workflow_filter:
            workflows_to_show = {k: v for k, v in self.data_store.workflows.items() if k in workflow_filter}
        console.print(format_workflow_choices(
            workflows_to_show,
            default=suggestion,
            confidence=confidence
        ))

        # Get input
        prompt = get_workflow_prompt(suggestion)

        while True:
            choice = input(prompt).strip().lower()

            # Handle empty input (accept default/confirm)
            if not choice and suggestion:
                selected = suggestion
                # Send feedback: user confirmed the suggestion
                if arch_result.get("decision_id"):
                    try:
                        from mailflow.archivist_integration import record_feedback
                        await record_feedback(int(arch_result["decision_id"]), selected, "confirmed")
                    except Exception as e:
                        logger.debug(f"archivist feedback not recorded: {e}")
                break

            # Handle skip (s) or next (n) - no feedback for skips per SOT
            if choice in ('s', 'n'):
                return None

            # Handle expand
            if choice == 'e':
                body = email_data.get('body', '')
                console.print(Panel(body, title="Full Content"))
                continue

            # Handle help
            if choice == '?':
                console.print("Enter: confirm suggestion | 1-9: correct to workflow | s: skip | e: expand | new: create workflow")
                continue

            # Handle 'new' for workflow creation
            if choice == 'new':
                selected = self._create_new_workflow()
                if selected:
                    # Send feedback: user corrected to new workflow
                    if arch_result.get("decision_id"):
                        try:
                            from mailflow.archivist_integration import record_feedback
                            await record_feedback(int(arch_result["decision_id"]), selected, "corrected")
                        except Exception as e:
                            logger.debug(f"archivist feedback not recorded: {e}")
                    break
                continue

            # Handle number selection (correction)
            if choice.isdigit():
                idx = int(choice) - 1
                workflow_names = sorted(workflows_to_show.keys())
                if 0 <= idx < len(workflow_names):
                    selected = workflow_names[idx]
                    # Send feedback: user corrected (if different from suggestion) or confirmed
                    if arch_result.get("decision_id"):
                        try:
                            from mailflow.archivist_integration import record_feedback
                            reason = "confirmed" if selected == suggestion else "corrected"
                            await record_feedback(int(arch_result["decision_id"]), selected, reason)
                        except Exception as e:
                            logger.debug(f"archivist feedback not recorded: {e}")
                    break
                else:
                    console.print(f"Invalid number: {choice}", style="red")
                    continue

            # Handle workflow name (correction)
            if choice in workflows_to_show:
                selected = choice
                # Send feedback: user corrected or confirmed
                if arch_result.get("decision_id"):
                    try:
                        from mailflow.archivist_integration import record_feedback
                        reason = "confirmed" if selected == suggestion else "corrected"
                        await record_feedback(int(arch_result["decision_id"]), selected, reason)
                    except Exception as e:
                        logger.debug(f"archivist feedback not recorded: {e}")
                break

            console.print(f"Unknown choice: {choice}", style="red")

        return selected

    def _display_classification_evidence(self, console: Console, arch_result: dict, suggestion: str | None, confidence: float) -> None:
        """Display classification evidence in interactive mode."""
        from rich.table import Table

        # Build evidence panel
        evidence_lines = []

        if suggestion:
            evidence_lines.append(f"[bold]Proposed:[/bold] {suggestion} ({confidence:.0%} confidence)")
        else:
            evidence_lines.append("[bold]Proposed:[/bold] [dim]null (no match)[/dim]")

        # Show which advisors were used
        advisors = arch_result.get("advisors_used") or []
        if advisors:
            evidence_lines.append(f"[dim]Advisors: {', '.join(advisors)}[/dim]")

        # Show LLM rationale if available
        rationale = arch_result.get("rationale") or arch_result.get("evidence", {}).get("rationale")
        if rationale:
            evidence_lines.append(f"[dim]Rationale: {rationale}[/dim]")

        # Show top neighbors if available
        neighbors = arch_result.get("neighbors") or arch_result.get("evidence", {}).get("neighbors") or []
        if neighbors:
            evidence_lines.append("[dim]Similar past decisions:[/dim]")
            for neighbor in neighbors[:3]:
                if isinstance(neighbor, dict):
                    n_label = neighbor.get("label", "?")
                    n_score = neighbor.get("score", 0)
                    evidence_lines.append(f"  [dim]• {n_label} ({n_score:.0%})[/dim]")
                elif isinstance(neighbor, (list, tuple)) and len(neighbor) >= 2:
                    evidence_lines.append(f"  [dim]• {neighbor[0]} ({neighbor[1]:.0%})[/dim]")

        if evidence_lines:
            console.print(Panel("\n".join(evidence_lines), title="Classification", border_style="blue"))

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
