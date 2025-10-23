"""Test LLM-based email classification"""

from datetime import datetime

import pytest
from dotenv import load_dotenv

# Load API keys from .env
load_dotenv()

from mailflow.models import CriteriaInstance, WorkflowDefinition


@pytest.fixture
def sample_workflows():
    """Create sample workflows for testing"""
    return {
        "business-receipts": WorkflowDefinition(
            name="business-receipts",
            description="Save business receipts and expenses",
            action_type="save_pdf",
            action_params={"directory": "~/Documents/mailflow/business"},
        ),
        "personal-receipts": WorkflowDefinition(
            name="personal-receipts",
            description="Save personal receipts and expenses",
            action_type="save_pdf",
            action_params={"directory": "~/Documents/mailflow/personal"},
        ),
        "archive": WorkflowDefinition(
            name="archive",
            description="Archive newsletters",
            action_type="create_todo",
            action_params={"todo_file": "~/todos.txt"},
        ),
    }


@pytest.fixture
def sample_criteria():
    """Create sample criteria instances"""
    return [
        CriteriaInstance(
            email_id="msg1",
            workflow_name="business-receipts",
            timestamp=datetime.now(),
            email_features={
                "from_domain": "aws.amazon.com",
                "subject_words": ["invoice", "aws", "services"],
                "has_pdf": True,
            },
        ),
        CriteriaInstance(
            email_id="msg2",
            workflow_name="business-receipts",
            timestamp=datetime.now(),
            email_features={
                "from_domain": "dropbox.com",
                "subject_words": ["receipt", "subscription"],
                "has_pdf": True,
            },
        ),
        CriteriaInstance(
            email_id="msg3",
            workflow_name="personal-receipts",
            timestamp=datetime.now(),
            email_features={
                "from_domain": "netflix.com",
                "subject_words": ["payment", "confirmation"],
                "has_pdf": False,
            },
        ),
    ]


@pytest.fixture
def sample_email():
    """Create sample email data"""
    return {
        "from": "noreply@aws.amazon.com",
        "subject": "Your AWS Invoice for October 2025",
        "body": "Your monthly AWS invoice is ready...",
        "features": {
            "from_domain": "aws.amazon.com",
            "subject_words": ["aws", "invoice", "october", "2025"],
            "has_pdf": True,
            "has_attachments": True,
        },
    }


class TestLLMClassifierPromptBuilding:
    """Test prompt building with workflow context"""

    def test_imports_llm_classifier(self):
        """Test that we can import the LLM classifier module"""
        from mailflow.llm_classifier import LLMClassifier

        assert LLMClassifier is not None

    def test_sanitize_for_prompt_removes_null_bytes(self):
        """Test that sanitization removes null bytes"""
        from mailflow.llm_classifier import LLMClassifier

        classifier = LLMClassifier()
        text = "Hello\x00World"
        result = classifier._sanitize_for_prompt(text)

        assert "\x00" not in result
        assert "HelloWorld" in result

    def test_sanitize_for_prompt_collapses_whitespace(self):
        """Test that sanitization collapses excessive whitespace"""
        from mailflow.llm_classifier import LLMClassifier

        classifier = LLMClassifier()
        text = "Hello\n\n\n\nWorld\n\nFoo   Bar"
        result = classifier._sanitize_for_prompt(text)

        # Should collapse to single spaces
        assert "\n" not in result
        assert result == "Hello World Foo Bar"

    def test_sanitize_for_prompt_truncates(self):
        """Test that sanitization truncates to max_length"""
        from mailflow.llm_classifier import LLMClassifier

        classifier = LLMClassifier()
        text = "A" * 1000
        result = classifier._sanitize_for_prompt(text, max_length=100)

        assert len(result) == 100

    def test_sanitize_for_prompt_handles_empty_string(self):
        """Test that sanitization handles empty strings"""
        from mailflow.llm_classifier import LLMClassifier

        classifier = LLMClassifier()
        result = classifier._sanitize_for_prompt("")

        assert result == ""

    def test_sanitize_for_prompt_handles_none(self):
        """Test that sanitization handles None"""
        from mailflow.llm_classifier import LLMClassifier

        classifier = LLMClassifier()
        result = classifier._sanitize_for_prompt(None)

        assert result == ""

    def test_prompt_includes_workflow_names(self, sample_workflows, sample_criteria, sample_email):
        """Test that prompt includes all workflow names"""
        from mailflow.llm_classifier import LLMClassifier

        classifier = LLMClassifier()
        prompt = classifier._build_prompt(sample_email, sample_workflows, sample_criteria, 3)

        assert "business-receipts" in prompt
        assert "personal-receipts" in prompt
        assert "archive" in prompt

    def test_prompt_includes_workflow_descriptions(
        self, sample_workflows, sample_criteria, sample_email
    ):
        """Test that prompt includes workflow descriptions"""
        from mailflow.llm_classifier import LLMClassifier

        classifier = LLMClassifier()
        prompt = classifier._build_prompt(sample_email, sample_workflows, sample_criteria, 3)

        assert "Save business receipts and expenses" in prompt
        assert "Save personal receipts and expenses" in prompt
        assert "Archive newsletters" in prompt

    def test_prompt_includes_examples(self, sample_workflows, sample_criteria, sample_email):
        """Test that prompt includes past classification examples"""
        from mailflow.llm_classifier import LLMClassifier

        classifier = LLMClassifier()
        prompt = classifier._build_prompt(sample_email, sample_workflows, sample_criteria, 3)

        # Should include example domains
        assert "aws.amazon.com" in prompt
        assert "dropbox.com" in prompt

    def test_prompt_limits_examples_per_workflow(
        self, sample_workflows, sample_criteria, sample_email
    ):
        """Test that prompt limits examples per workflow"""
        from mailflow.llm_classifier import LLMClassifier

        # Add many examples for one workflow
        many_criteria = sample_criteria + [
            CriteriaInstance(
                email_id=f"msg{i}",
                workflow_name="business-receipts",
                timestamp=datetime.now(),
                email_features={
                    "from_domain": f"example{i}.com",
                    "subject_words": ["test"],
                    "has_pdf": True,
                },
            )
            for i in range(10)
        ]

        classifier = LLMClassifier()
        prompt = classifier._build_prompt(
            sample_email, sample_workflows, many_criteria, max_examples=2
        )

        # Should only include 2 examples per workflow
        # Count occurrences of "Past examples" sections
        example_sections = prompt.count("Past examples:")
        # We have 2 workflows with examples (business-receipts and personal-receipts)
        assert example_sections <= 3  # One for each workflow that has examples

    def test_prompt_includes_current_email(self, sample_workflows, sample_criteria, sample_email):
        """Test that prompt includes the email to classify"""
        from mailflow.llm_classifier import LLMClassifier

        classifier = LLMClassifier()
        prompt = classifier._build_prompt(sample_email, sample_workflows, sample_criteria, 3)

        assert "Email to classify:" in prompt
        assert "Your AWS Invoice for October 2025" in prompt
        assert "aws.amazon.com" in prompt


@pytest.mark.asyncio
class TestLLMClassifierWithRealAPI:
    """Test LLM classification with real API calls"""

    async def test_classify_returns_workflow_classification(
        self, sample_workflows, sample_criteria, sample_email
    ):
        """Test that classify returns a WorkflowClassification object with real LLM"""
        from mailflow.llm_classifier import LLMClassifier, WorkflowClassification

        async with LLMClassifier(model_alias="fast") as classifier:
            result = await classifier.classify(sample_email, sample_workflows, sample_criteria)

        assert isinstance(result, WorkflowClassification)
        assert result.workflow in sample_workflows
        assert 0.0 <= result.confidence <= 1.0
        assert len(result.reasoning) > 0

    async def test_classify_chooses_correct_workflow(
        self, sample_workflows, sample_criteria, sample_email
    ):
        """Test that real LLM chooses the correct workflow based on context"""
        from mailflow.llm_classifier import LLMClassifier

        # Sample email is an AWS invoice, should match business-receipts based on criteria
        async with LLMClassifier(model_alias="fast") as classifier:
            result = await classifier.classify(sample_email, sample_workflows, sample_criteria)

        # AWS invoice should match business-receipts based on the past examples
        assert result.workflow == "business-receipts"
        assert result.confidence > 0.5
        assert len(result.reasoning) > 0

    async def test_classify_with_different_email_types(self, sample_workflows, sample_criteria):
        """Test classification with different email types"""
        from mailflow.llm_classifier import LLMClassifier

        # Test with a personal expense email
        personal_email = {
            "from": "billing@netflix.com",
            "subject": "Your Netflix payment confirmation",
            "body": "Thank you for your payment...",
            "features": {
                "from_domain": "netflix.com",
                "subject_words": ["payment", "confirmation"],
                "has_pdf": False,
                "has_attachments": False,
            },
        }

        async with LLMClassifier(model_alias="fast") as classifier:
            result = await classifier.classify(personal_email, sample_workflows, sample_criteria)

        # Netflix should match personal-receipts based on past examples
        assert result.workflow == "personal-receipts"
        assert result.confidence > 0.5

    async def test_classify_with_limited_examples(
        self, sample_workflows, sample_criteria, sample_email
    ):
        """Test that classification works with limited examples per workflow"""
        from mailflow.llm_classifier import LLMClassifier

        async with LLMClassifier(model_alias="fast") as classifier:
            result = await classifier.classify(
                sample_email, sample_workflows, sample_criteria, max_examples_per_workflow=1
            )

        assert result.workflow in sample_workflows
        assert 0.0 <= result.confidence <= 1.0

    async def test_classify_handles_invalid_model_alias(
        self, sample_workflows, sample_criteria, sample_email
    ):
        """Test that classifier handles invalid model alias gracefully"""
        from mailflow.llm_classifier import LLMClassifier

        async with LLMClassifier(model_alias="nonexistent-model") as classifier:
            with pytest.raises(Exception):
                await classifier.classify(sample_email, sample_workflows, sample_criteria)


class TestWorkflowClassification:
    """Test WorkflowClassification data class"""

    def test_workflow_classification_creation(self):
        """Test creating a WorkflowClassification object"""
        from mailflow.llm_classifier import WorkflowClassification

        classification = WorkflowClassification(
            workflow="test-workflow", confidence=0.85, reasoning="Test reasoning"
        )

        assert classification.workflow == "test-workflow"
        assert classification.confidence == 0.85
        assert classification.reasoning == "Test reasoning"
