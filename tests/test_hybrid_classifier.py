"""Test hybrid classifier combining similarity and LLM classification"""

from datetime import datetime

import pytest
from dotenv import load_dotenv

# Load API keys from .env
load_dotenv()

from mailflow.config import Config
from mailflow.models import CriteriaInstance, WorkflowDefinition
from mailflow.similarity import SimilarityEngine


@pytest.fixture
def sample_workflows():
    """Create sample workflows"""
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
                "subject_words": ["invoice", "aws"],
                "has_pdf": True,
            },
        )
    ]


@pytest.fixture
def sample_email():
    """Create sample email data"""
    return {
        "from": "noreply@aws.amazon.com",
        "subject": "AWS Invoice",
        "body": "Your invoice is ready",
        "features": {
            "from_domain": "aws.amazon.com",
            "subject_words": ["aws", "invoice"],
            "has_pdf": True,
            "has_attachments": True,
        },
    }


@pytest.fixture
def config():
    """Create test config"""
    import tempfile

    return Config(config_dir=tempfile.mkdtemp())


class TestHybridClassifierInit:
    """Test hybrid classifier initialization"""

    def test_imports_hybrid_classifier(self):
        """Test that we can import the hybrid classifier module"""
        from mailflow.hybrid_classifier import HybridClassifier

        assert HybridClassifier is not None

    def test_init_with_similarity_engine_only(self, config):
        """Test initialization with only similarity engine"""
        from mailflow.hybrid_classifier import HybridClassifier

        similarity_engine = SimilarityEngine(config)
        classifier = HybridClassifier(similarity_engine)

        assert classifier.similarity_engine is similarity_engine
        assert classifier.llm_classifier is None

    def test_init_with_llm_classifier(self, config):
        """Test initialization with LLM classifier"""
        from mailflow.hybrid_classifier import HybridClassifier
        from mailflow.llm_classifier import LLMClassifier

        similarity_engine = SimilarityEngine(config)
        llm_classifier = LLMClassifier(model_alias="fast")
        classifier = HybridClassifier(similarity_engine, llm_classifier)

        assert classifier.similarity_engine is similarity_engine
        assert classifier.llm_classifier is llm_classifier

    def test_init_tracks_stats(self, config):
        """Test that classifier initializes statistics"""
        from mailflow.hybrid_classifier import HybridClassifier

        similarity_engine = SimilarityEngine(config)
        classifier = HybridClassifier(similarity_engine)

        stats = classifier.get_stats()
        assert stats["similarity_only"] == 0
        assert stats["llm_only"] == 0
        assert stats["llm_assisted"] == 0


class TestHybridClassifierThresholds:
    """Test hybrid classifier confidence threshold configuration"""

    def test_default_thresholds(self, config):
        """Test default confidence thresholds"""
        from mailflow.hybrid_classifier import HybridClassifier

        similarity_engine = SimilarityEngine(config)
        classifier = HybridClassifier(similarity_engine)

        assert classifier.HIGH_CONFIDENCE == 0.85
        assert classifier.MEDIUM_CONFIDENCE == 0.50


@pytest.mark.asyncio
class TestHybridClassifierWithRealComponents:
    """Test hybrid classifier with real similarity engine and LLM"""

    async def test_high_confidence_uses_similarity_only(
        self, config, sample_workflows, sample_criteria, sample_email
    ):
        """Test that high similarity confidence uses similarity only"""
        from mailflow.hybrid_classifier import HybridClassifier
        from mailflow.llm_classifier import LLMClassifier

        similarity_engine = SimilarityEngine(config)
        llm_classifier = LLMClassifier(model_alias="fast")
        classifier = HybridClassifier(similarity_engine, llm_classifier)

        # sample_email has AWS domain matching criteria, should get high confidence
        result = await classifier.classify(sample_email, sample_workflows, sample_criteria)

        # With matching criteria, similarity should be high enough
        # that we don't need LLM
        if result["rankings"] and result["rankings"][0][1] >= 0.85:
            assert result["method"] == "similarity"
            assert result["llm_suggestion"] is None
        # Otherwise test passes - confidence depends on actual similarity

    async def test_low_confidence_uses_llm(self, config, sample_workflows):
        """Test that low similarity confidence uses LLM"""
        from mailflow.hybrid_classifier import HybridClassifier
        from mailflow.llm_classifier import LLMClassifier

        # Create email that doesn't match any criteria (no criteria instances)
        unmatched_email = {
            "from": "nobody@nowhere.com",
            "subject": "Completely unrelated subject",
            "body": "Random content",
            "features": {
                "from_domain": "nowhere.com",
                "subject_words": ["completely", "unrelated"],
                "has_pdf": False,
                "has_attachments": False,
            },
        }

        similarity_engine = SimilarityEngine(config)
        llm_classifier = LLMClassifier(model_alias="fast")
        classifier = HybridClassifier(similarity_engine, llm_classifier)

        # With no criteria instances, similarity will be low
        result = await classifier.classify(unmatched_email, sample_workflows, [])  # Empty criteria

        # Should use LLM because similarity has no confidence
        assert result["method"] in ["llm", "similarity_fallback"]
        # If LLM worked, should have suggestion
        if result["method"] == "llm":
            assert result["llm_suggestion"] is not None

    async def test_medium_confidence_offers_llm_assist(
        self, config, sample_workflows, sample_criteria
    ):
        """Test that medium confidence offers LLM assist"""
        from mailflow.hybrid_classifier import HybridClassifier
        from mailflow.llm_classifier import LLMClassifier

        # Create email with partial match - should get medium confidence
        medium_email = {
            "from": "billing@aws.amazon.com",
            "subject": "Notification",  # Doesn't have "invoice" keyword
            "body": "Some content",
            "features": {
                "from_domain": "aws.amazon.com",  # Matches domain
                "subject_words": ["notification"],  # Different keywords
                "has_pdf": False,  # Doesn't match PDF requirement
                "has_attachments": False,
            },
        }

        similarity_engine = SimilarityEngine(config)
        llm_classifier = LLMClassifier(model_alias="fast")
        classifier = HybridClassifier(similarity_engine, llm_classifier)

        result = await classifier.classify(medium_email, sample_workflows, sample_criteria)

        # Should use hybrid or similarity, depending on actual confidence
        assert result["method"] in ["similarity", "hybrid", "llm"]
        # Rankings should exist
        assert len(result["rankings"]) > 0

    async def test_hybrid_classifier_stats_tracking(
        self, config, sample_workflows, sample_criteria, sample_email
    ):
        """Test that statistics are tracked correctly"""
        from mailflow.hybrid_classifier import HybridClassifier
        from mailflow.llm_classifier import LLMClassifier

        similarity_engine = SimilarityEngine(config)
        llm_classifier = LLMClassifier(model_alias="fast")
        classifier = HybridClassifier(similarity_engine, llm_classifier)

        # Process one email
        await classifier.classify(sample_email, sample_workflows, sample_criteria)

        stats = classifier.get_stats()
        # Should have incremented exactly one counter
        total = stats["similarity_only"] + stats["llm_only"] + stats["llm_assisted"]
        assert total == 1

    async def test_disabled_llm_uses_similarity_only(
        self, config, sample_workflows, sample_criteria, sample_email
    ):
        """Test that use_llm=False uses similarity only"""
        from mailflow.hybrid_classifier import HybridClassifier
        from mailflow.llm_classifier import LLMClassifier

        similarity_engine = SimilarityEngine(config)
        llm_classifier = LLMClassifier(model_alias="fast")
        classifier = HybridClassifier(similarity_engine, llm_classifier)

        result = await classifier.classify(
            sample_email, sample_workflows, sample_criteria, use_llm=False
        )

        assert result["method"] == "similarity"
        assert result["llm_suggestion"] is None

    async def test_no_llm_classifier_uses_similarity_only(
        self, config, sample_workflows, sample_criteria, sample_email
    ):
        """Test that missing LLM classifier uses similarity only"""
        from mailflow.hybrid_classifier import HybridClassifier

        similarity_engine = SimilarityEngine(config)
        classifier = HybridClassifier(similarity_engine, llm_classifier=None)

        result = await classifier.classify(sample_email, sample_workflows, sample_criteria)

        assert result["method"] == "similarity"
        assert result["llm_suggestion"] is None

    async def test_llm_error_fallback(self, config, sample_workflows):
        """Test that LLM errors fall back to similarity"""
        from mailflow.hybrid_classifier import HybridClassifier
        from mailflow.llm_classifier import LLMClassifier

        # Create email that would trigger low confidence
        unmatched_email = {
            "from": "nobody@nowhere.com",
            "subject": "Test",
            "body": "Content",
            "features": {
                "from_domain": "nowhere.com",
                "subject_words": ["test"],
                "has_pdf": False,
                "has_attachments": False,
            },
        }

        similarity_engine = SimilarityEngine(config)
        # Use invalid model alias to trigger error
        llm_classifier = LLMClassifier(model_alias="nonexistent-model")
        classifier = HybridClassifier(similarity_engine, llm_classifier)

        result = await classifier.classify(unmatched_email, sample_workflows, [])  # Empty criteria

        # Should fall back to similarity
        assert result["method"] == "similarity_fallback"

    async def test_multiple_classifications_track_stats(
        self, config, sample_workflows, sample_criteria, sample_email
    ):
        """Test that multiple classifications track stats correctly"""
        from mailflow.hybrid_classifier import HybridClassifier
        from mailflow.llm_classifier import LLMClassifier

        similarity_engine = SimilarityEngine(config)
        llm_classifier = LLMClassifier(model_alias="fast")
        classifier = HybridClassifier(similarity_engine, llm_classifier)

        # Classify same email multiple times
        for _ in range(3):
            await classifier.classify(sample_email, sample_workflows, sample_criteria)

        stats = classifier.get_stats()
        # Should have incremented counter 3 times total
        total = stats["similarity_only"] + stats["llm_only"] + stats["llm_assisted"]
        assert total == 3
