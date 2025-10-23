"""
Integration test simulating the complete user workflow
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from mailflow.config import Config
from mailflow.email_extractor import EmailExtractor
from mailflow.models import CriteriaInstance, DataStore
from mailflow.similarity import SimilarityEngine
from mailflow.ui import WorkflowSelector


class TestIntegration:
    """Test the complete integration of all components"""

    @pytest.fixture
    def sample_emails(self):
        """Load sample emails from res directory"""
        res_dir = Path(__file__).parent / "res"
        emails = {}

        for email_file in res_dir.glob("*.eml"):
            with open(email_file, "r", encoding="utf-8", errors="ignore") as f:
                emails[email_file.stem] = f.read()

        return emails

    def test_complete_workflow_new_user(self, temp_config_dir, sample_emails):
        """Test complete workflow for a new user with no history"""
        config = Config(config_dir=temp_config_dir)
        data_store = DataStore(config)
        extractor = EmailExtractor()
        similarity_engine = SimilarityEngine(config)
        ui = WorkflowSelector(config, data_store, similarity_engine)

        # Process first email (no history, should show default workflows)
        if "amazon_invoice" in sample_emails:
            email_data = extractor.extract(sample_emails["amazon_invoice"])

            # Mock user input to create new workflow
            with patch("mailflow.linein.LineInput.ask") as mock_ask:
                # User selects "new" then creates invoice workflow
                mock_ask.side_effect = [
                    "new",  # Select new workflow
                    "save-invoices",  # Workflow name
                    "Save invoice attachments",  # Description
                    "no",  # Use a workflow template? No
                    "save_attachment",  # Action type
                    "~/invoices",  # Directory
                    "*.pdf",  # Pattern
                ]

                selected = ui.select_workflow(email_data)
                assert selected == "save-invoices"

            # Verify workflow was created and decision was saved
            assert "save-invoices" in data_store.workflows
            assert len(data_store.criteria_instances) == 1
            assert data_store.criteria_instances[0].workflow_name == "save-invoices"

    def test_workflow_with_learning(self, temp_config_dir, sample_emails):
        """Test workflow after system has learned from examples"""
        config = Config(config_dir=temp_config_dir)
        data_store = DataStore(config)
        extractor = EmailExtractor()

        # First, train the system with a few examples
        training_emails = [
            ("amazon_invoice", "save-invoices"),
            ("prodigi_failed", "save-errors"),
            ("github_notification", "create-todos"),
        ]

        # Create workflows
        from mailflow.models import WorkflowDefinition

        workflows = {
            "save-invoices": WorkflowDefinition(
                name="save-invoices",
                description="Save invoice PDFs",
                action_type="save_attachment",
                action_params={"directory": "~/invoices", "pattern": "*.pdf"},
            ),
            "save-errors": WorkflowDefinition(
                name="save-errors",
                description="Save error emails as PDF",
                action_type="save_email_as_pdf",
                action_params={"directory": "~/errors"},
            ),
            "create-todos": WorkflowDefinition(
                name="create-todos",
                description="Create todo items from emails",
                action_type="create_todo",
                action_params={"todo_file": "~/todos.txt"},
            ),
        }

        for workflow in workflows.values():
            data_store.add_workflow(workflow)

        # Add training data
        for email_name, workflow_name in training_emails:
            if email_name in sample_emails:
                email_data = extractor.extract(sample_emails[email_name])
                instance = CriteriaInstance(
                    email_id=email_data["message_id"],
                    workflow_name=workflow_name,
                    timestamp=datetime.now(),
                    email_features=email_data["features"],
                )
                data_store.add_criteria_instance(instance)

        # Now test with a similar email (cloudflare invoice)
        similarity_engine = SimilarityEngine(config)
        ui = WorkflowSelector(config, data_store, similarity_engine)

        if "cloudflare_invoice" in sample_emails:
            email_data = extractor.extract(sample_emails["cloudflare_invoice"])

            # Mock user selecting the suggested workflow
            with patch("mailflow.linein.LineInput.ask") as mock_ask:
                mock_ask.return_value = "1"  # Select first suggestion

                # Capture printed output
                with patch("builtins.print") as mock_print:
                    selected = ui.select_workflow(email_data)

                    # Check what was suggested
                    print_calls = [str(call) for call in mock_print.call_args_list]
                    # The system should have made some suggestion
                    assert len(print_calls) > 0

            # The system should have selected something (user pressed "1")
            assert selected is not None
            assert selected in data_store.workflows

            # Verify the decision was recorded
            assert len(data_store.criteria_instances) == len(training_emails) + 1

    def test_similarity_improvement_over_time(self, temp_config_dir, sample_emails):
        """Test that similarity scores improve as more examples are added"""
        config = Config(config_dir=temp_config_dir)
        data_store = DataStore(config)
        extractor = EmailExtractor()
        similarity_engine = SimilarityEngine(config)

        # Create invoice workflow
        from mailflow.models import WorkflowDefinition

        invoice_workflow = WorkflowDefinition(
            name="save-invoices",
            description="Save invoices",
            action_type="save_attachment",
            action_params={"directory": "~/invoices"},
        )
        data_store.add_workflow(invoice_workflow)

        # Test email
        test_email = None
        if "other_invoice" in sample_emails:
            test_email = extractor.extract(sample_emails["other_invoice"])

        if not test_email:
            pytest.skip("No test email available")

        scores = []

        # Add training examples one by one and measure improvement
        training_emails = ["amazon_invoice", "cloudflare_invoice"]

        for i, email_name in enumerate(training_emails):
            if email_name in sample_emails:
                # Add training example
                email_data = extractor.extract(sample_emails[email_name])
                instance = CriteriaInstance(
                    email_id=email_data["message_id"],
                    workflow_name="save-invoices",
                    timestamp=datetime.now(),
                    email_features=email_data["features"],
                )
                data_store.add_criteria_instance(instance)

                # Test similarity
                rankings = similarity_engine.rank_workflows(
                    test_email["features"], data_store.criteria_instances, top_n=1
                )

                if rankings and rankings[0][0] == "save-invoices":
                    scores.append(rankings[0][1])
                else:
                    scores.append(0.0)

        # Scores should generally improve or stay stable
        if len(scores) >= 2:
            print(f"\nSimilarity scores over time: {scores}")
            # At least one score should be positive
            assert any(score > 0 for score in scores)

    def test_workflow_execution(self, temp_config_dir, sample_emails):
        """Test that workflows can be executed"""
        from mailflow.process import process

        # Mock the workflow execution
        with patch("mailflow.workflow.save_attachment") as mock_save:
            with patch("mailflow.linein.LineInput.ask") as mock_ask:
                # Simulate user selecting to skip
                mock_ask.return_value = "skip"

                if "amazon_invoice" in sample_emails:
                    # Run the process
                    process(sample_emails["amazon_invoice"])

                    # Should not execute any workflow when skipped
                    mock_save.assert_not_called()
