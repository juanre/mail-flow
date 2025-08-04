#!/usr/bin/env python
"""
Demo script showing the pmail learning workflow
"""
import sys
import os
from pathlib import Path
from datetime import datetime

# Add src to path for demo
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from pmail.config import Config
from pmail.email_extractor import EmailExtractor
from pmail.models import DataStore, CriteriaInstance, WorkflowDefinition
from pmail.similarity import SimilarityEngine
from pmail.ui import WorkflowSelector


def load_sample_emails():
    """Load sample emails from tests/res"""
    res_dir = Path(__file__).parent / "tests" / "res"
    emails = {}

    for email_file in res_dir.glob("*.eml"):
        with open(email_file, "r", encoding="utf-8", errors="ignore") as f:
            emails[email_file.stem] = f.read()

    return emails


def setup_workflows(data_store):
    """Set up initial workflows"""
    print("\n=== Setting up workflows ===")

    workflows = [
        WorkflowDefinition(
            name="save-invoices",
            description="Save invoice PDFs to ~/invoices",
            action_type="save_attachment",
            action_params={"directory": "~/invoices", "pattern": "*.pdf"},
        ),
        WorkflowDefinition(
            name="flag-errors",
            description="Flag error notifications",
            action_type="flag",
            action_params={"flag": "error"},
        ),
        WorkflowDefinition(
            name="archive-updates",
            description="Archive software updates",
            action_type="flag",
            action_params={"flag": "archived"},
        ),
    ]

    for workflow in workflows:
        data_store.add_workflow(workflow)
        print(f"  Added workflow: {workflow.name}")


def train_system(config, emails):
    """Train the system with sample emails"""
    print("\n=== Training Phase ===")

    data_store = DataStore(config)
    setup_workflows(data_store)

    extractor = EmailExtractor()

    # Training data
    training = [
        ("amazon_invoice", "save-invoices", "Amazon invoice"),
        ("cloudflare_invoice", "save-invoices", "Cloudflare invoice"),
        ("prodigi_failed", "flag-errors", "Prodigi error notification"),
        ("dropbox_update", "archive-updates", "Dropbox update"),
    ]

    for email_name, workflow, description in training:
        if email_name in emails:
            print(f"\n  Training with: {description}")
            email_data = extractor.extract(emails[email_name])

            instance = CriteriaInstance(
                email_id=email_data["message_id"],
                workflow_name=workflow,
                timestamp=datetime.now(),
                email_features=email_data["features"],
                user_confirmed=True,
                confidence_score=1.0,
            )

            data_store.add_criteria_instance(instance)
            print(f"    -> Assigned to '{workflow}' workflow")

            # Show what features were extracted
            print(
                f"    Features: domain={email_data['features'].get('from_domain', 'N/A')}, "
                f"has_pdf={email_data['features'].get('has_pdf', False)}"
            )


def test_system(config, emails):
    """Test the system with new emails"""
    print("\n=== Testing Phase ===")

    data_store = DataStore(config)
    extractor = EmailExtractor()
    similarity_engine = SimilarityEngine(config)

    # Test with emails not in training set
    test_emails = ["other_invoice", "github_notification"]

    for email_name in test_emails:
        if email_name in emails:
            print(f"\n  Testing with: {email_name}")
            email_data = extractor.extract(emails[email_name])

            # Get predictions
            rankings = similarity_engine.rank_workflows(
                email_data["features"], data_store.criteria_instances, top_n=3
            )

            print(f"    From: {email_data['from']}")
            print(f"    Subject: {email_data['subject']}")

            if rankings:
                print("\n    Predictions:")
                for i, (workflow_name, score, instances) in enumerate(rankings, 1):
                    workflow = data_store.workflows.get(workflow_name)
                    if workflow:
                        print(
                            f"      {i}. {workflow.description} ({score:.0%} confidence)"
                        )

                        # Show why it matched
                        if instances and score > 0.3:
                            best_instance = instances[0]
                            explanations = similarity_engine.get_feature_explanation(
                                email_data["features"], best_instance
                            )
                            if explanations:
                                print(
                                    f"         Reason: {', '.join(explanations.values())}"
                                )
            else:
                print("    No predictions available")


def interactive_demo(config, emails):
    """Interactive demo with user input"""
    print("\n=== Interactive Demo ===")
    print("Now let's process an email interactively...")

    # Use github notification as test
    if "github_notification" in emails:
        print("\nProcessing: GitHub notification email")

        # Import and use the process function with our demo config
        from pmail.process import process

        # Process the email (this will show UI and execute the workflow)
        process(emails["github_notification"], config=config)


def main():
    """Run the complete demo"""
    print("=== pmail Learning Demo ===")
    print("This demo shows how pmail learns from your email classification choices.")

    # Load sample emails
    emails = load_sample_emails()
    print(f"\nLoaded {len(emails)} sample emails")

    # Use temporary config for demo
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        config = Config(config_dir=temp_dir)
        print(f"Using temporary config directory: {temp_dir}")

        # Phase 1: Train the system
        train_system(config, emails)

        # Phase 2: Test the system
        test_system(config, emails)

        # Phase 3: Interactive demo
        print("\n" + "=" * 60)
        input("Press Enter to see the interactive UI demo...")
        interactive_demo(config, emails)

    print("\n=== Demo Complete ===")
    print("In real usage, pmail would:")
    print("  1. Learn from every email you classify")
    print("  2. Get better at predicting the right workflow over time")
    print("  3. Execute the selected workflow (save attachments, flag emails, etc.)")


if __name__ == "__main__":
    main()
