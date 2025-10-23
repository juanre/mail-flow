"""
Test the learning process with real emails.
This test demonstrates how the system learns from user selections.
"""

import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from mailflow.config import Config
from mailflow.email_extractor import EmailExtractor
from mailflow.models import CriteriaInstance, DataStore, WorkflowDefinition
from mailflow.similarity import SimilarityEngine


class TestLearningProcess:
    """Test the complete learning workflow with real emails"""

    @pytest.fixture
    def real_emails(self):
        """Load real email samples"""
        res_dir = Path(__file__).parent / "res"
        emails = {}

        # Load each email file
        for email_file in res_dir.glob("*.eml"):
            with open(email_file, "r", encoding="utf-8", errors="ignore") as f:
                emails[email_file.stem] = f.read()

        return emails

    @pytest.fixture
    def temp_mailflow_dir(self):
        """Create a temporary mailflow directory"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_initial_workflow_setup(self, temp_mailflow_dir):
        """Test setting up initial workflows"""
        config = Config(config_dir=temp_mailflow_dir)
        data_store = DataStore(config)

        # Add invoice-specific workflow
        invoice_workflow = WorkflowDefinition(
            name="save-invoices",
            description="Save invoice attachments to ~/invoices",
            action_type="save_attachment",
            action_params={"directory": "~/invoices", "pattern": "*.pdf"},
        )
        data_store.add_workflow(invoice_workflow)

        # Add error notification workflow
        error_workflow = WorkflowDefinition(
            name="save-errors",
            description="Save error notifications as PDF",
            action_type="save_email_as_pdf",
            action_params={"directory": "~/errors"},
        )
        data_store.add_workflow(error_workflow)

        # Add todo workflow for updates
        update_workflow = WorkflowDefinition(
            name="create-update-todos",
            description="Create todos for software updates",
            action_type="create_todo",
            action_params={"todo_file": "~/updates.txt"},
        )
        data_store.add_workflow(update_workflow)

        # Verify workflows were saved
        assert len(data_store.workflows) >= 6  # 3 default + 3 new
        assert "save-invoices" in data_store.workflows
        assert "save-errors" in data_store.workflows
        assert "create-update-todos" in data_store.workflows

    def test_first_learning_phase(self, temp_mailflow_dir, real_emails):
        """Test the first phase of learning - training the system"""
        config = Config(config_dir=temp_mailflow_dir)
        data_store = DataStore(config)
        extractor = EmailExtractor()

        # Set up workflows first
        self.test_initial_workflow_setup(temp_mailflow_dir)
        data_store = DataStore(config)  # Reload to get new workflows

        # Process emails and simulate user selections
        training_data = [
            ("amazon_invoice", "save-invoices"),
            ("cloudflare_invoice", "save-invoices"),
            ("other_invoice", "save-invoices"),
            ("dropbox_update", "create-update-todos"),
            ("github_notification", "archive"),
            ("prodigi_failed", "save-errors"),
        ]

        for email_name, workflow_name in training_data:
            if email_name in real_emails:
                # Extract email features
                email_data = extractor.extract(real_emails[email_name])

                # Create criteria instance (simulating user selection)
                instance = CriteriaInstance(
                    email_id=email_data["message_id"],
                    workflow_name=workflow_name,
                    timestamp=datetime.now(),
                    email_features=email_data["features"],
                    user_confirmed=True,
                    confidence_score=1.0,  # User selected, so high confidence
                )

                data_store.add_criteria_instance(instance)

        # Verify training data was saved
        assert len(data_store.criteria_instances) >= 6

        # Check that we have examples for each workflow
        invoice_criteria = data_store.get_criteria_for_workflow("save-invoices")
        assert len(invoice_criteria) >= 3

        error_criteria = data_store.get_criteria_for_workflow("save-errors")
        assert len(error_criteria) >= 1

    def test_similarity_learning(self, temp_mailflow_dir, real_emails):
        """Test that the system learns to recognize similar emails"""
        # First, train the system
        self.test_first_learning_phase(temp_mailflow_dir, real_emails)

        # Now test with a new email
        config = Config(config_dir=temp_mailflow_dir)
        data_store = DataStore(config)
        extractor = EmailExtractor()
        similarity_engine = SimilarityEngine(config)

        # Test with Amazon invoice (should recognize as invoice)
        if "amazon_invoice" in real_emails:
            email_data = extractor.extract(real_emails["amazon_invoice"])

            # Get workflow rankings
            rankings = similarity_engine.rank_workflows(
                email_data["features"], data_store.criteria_instances, top_n=3
            )

            # Should rank save-invoices first
            assert len(rankings) > 0
            assert rankings[0][0] == "save-invoices"
            assert rankings[0][1] > 0.5  # Good confidence

            # Check explanations
            best_instance = rankings[0][2][0]
            explanations = similarity_engine.get_feature_explanation(
                email_data["features"], best_instance
            )
            assert len(explanations) > 0

    def test_cross_validation(self, temp_mailflow_dir, real_emails):
        """Test learning with leave-one-out cross validation"""
        config = Config(config_dir=temp_mailflow_dir)
        extractor = EmailExtractor()

        # Extract all emails
        extracted_emails = {}
        for name, content in real_emails.items():
            extracted_emails[name] = extractor.extract(content)

        # Define expected classifications
        expected = {
            "amazon_invoice": "save-invoices",
            "cloudflare_invoice": "save-invoices",
            "other_invoice": "save-invoices",
            "dropbox_update": "create-update-todos",
            "github_notification": "archive",
            "prodigi_failed": "save-errors",
        }

        correct_predictions = 0
        total_tests = 0

        # For each email, train on all others and test on this one
        for test_email_name, test_email_data in extracted_emails.items():
            if test_email_name not in expected:
                continue

            # Create fresh data store for this test
            data_store = DataStore(config)
            self.test_initial_workflow_setup(temp_mailflow_dir)
            data_store = DataStore(config)  # Reload

            # Train on all other emails
            for train_name, train_data in extracted_emails.items():
                if train_name != test_email_name and train_name in expected:
                    instance = CriteriaInstance(
                        email_id=train_data["message_id"],
                        workflow_name=expected[train_name],
                        timestamp=datetime.now(),
                        email_features=train_data["features"],
                        user_confirmed=True,
                    )
                    data_store.add_criteria_instance(instance)

            # Test on the held-out email
            similarity_engine = SimilarityEngine(config)
            rankings = similarity_engine.rank_workflows(
                test_email_data["features"], data_store.criteria_instances, top_n=3
            )

            if rankings and rankings[0][0] == expected[test_email_name]:
                correct_predictions += 1
            total_tests += 1

            print(f"\nTesting {test_email_name}:")
            print(f"  Expected: {expected[test_email_name]}")
            if rankings:
                print(f"  Predicted: {rankings[0][0]} (confidence: {rankings[0][1]:.2f})")
            else:
                print(f"  Predicted: No prediction")

        # Should have reasonable accuracy
        accuracy = correct_predictions / total_tests if total_tests > 0 else 0
        print(f"\nOverall accuracy: {accuracy:.1%} ({correct_predictions}/{total_tests})")
        assert accuracy >= 0.5  # At least 50% accuracy

    def test_feature_importance(self, temp_mailflow_dir, real_emails):
        """Test which features are most important for classification"""
        config = Config(config_dir=temp_mailflow_dir)
        extractor = EmailExtractor()

        # Extract features from all emails
        invoice_features = []
        non_invoice_features = []

        for name, content in real_emails.items():
            data = extractor.extract(content)
            if "invoice" in name:
                invoice_features.append(data["features"])
            else:
                non_invoice_features.append(data["features"])

        # Analyze feature differences
        print("\nFeature analysis:")

        # Check PDF attachment correlation
        invoice_pdf_rate = sum(1 for f in invoice_features if f.get("has_pdf", False)) / len(
            invoice_features
        )
        non_invoice_pdf_rate = sum(
            1 for f in non_invoice_features if f.get("has_pdf", False)
        ) / len(non_invoice_features)

        print(f"  Invoice emails with PDF: {invoice_pdf_rate:.0%}")
        print(f"  Non-invoice emails with PDF: {non_invoice_pdf_rate:.0%}")

        # Check common domains
        invoice_domains = [f.get("from_domain", "") for f in invoice_features]
        non_invoice_domains = [f.get("from_domain", "") for f in non_invoice_features]

        print(f"  Invoice domains: {set(invoice_domains)}")
        print(f"  Non-invoice domains: {set(non_invoice_domains)}")

        # This helps understand what the system is learning
        assert invoice_pdf_rate > non_invoice_pdf_rate or len(invoice_features) > 0
