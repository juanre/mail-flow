from datetime import datetime, timedelta

import pytest

from mailflow.models import CriteriaInstance
from mailflow.similarity import SimilarityEngine


class TestSimilarityEngine:
    def test_jaccard_similarity(self, test_config):
        engine = SimilarityEngine(test_config)

        # Test identical sets
        assert engine._jaccard_similarity({"a", "b", "c"}, {"a", "b", "c"}) == 1.0

        # Test disjoint sets
        assert engine._jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0

        # Test partial overlap
        assert engine._jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"}) == 0.5

        # Test empty sets
        assert engine._jaccard_similarity(set(), set()) == 1.0
        assert engine._jaccard_similarity({"a"}, set()) == 0.0

    def test_calculate_similarity_domain_match(self, test_config):
        engine = SimilarityEngine(test_config)

        email_features = {
            "from_domain": "example.com",
            "subject_words": ["invoice", "payment"],
            "has_pdf": True,
        }

        criteria = CriteriaInstance(
            email_id="test1",
            workflow_name="archive",
            timestamp=datetime.now(),
            email_features={
                "from_domain": "example.com",
                "subject_words": ["invoice", "receipt"],
                "has_pdf": True,
            },
        )

        score = engine.calculate_similarity(email_features, criteria)

        # Should have high score due to matching domain and PDF
        assert score > 0.7

    def test_no_time_bias(self, test_config):
        """Test that age of criteria doesn't affect similarity score"""
        engine = SimilarityEngine(test_config)

        email_features = {
            "from_domain": "example.com",
            "subject_words": ["test"],
            "has_pdf": False,
        }

        # Create two identical criteria with different timestamps
        recent_criteria = CriteriaInstance(
            email_id="recent",
            workflow_name="archive",
            timestamp=datetime.now(),
            email_features=email_features.copy(),
        )

        old_criteria = CriteriaInstance(
            email_id="old",
            workflow_name="archive",
            timestamp=datetime.now() - timedelta(days=365),  # 1 year old
            email_features=email_features.copy(),
        )

        recent_score = engine.calculate_similarity(email_features, recent_criteria)
        old_score = engine.calculate_similarity(email_features, old_criteria)

        # Scores should be identical - age doesn't matter
        assert recent_score == old_score
        assert recent_score == 1.0  # Perfect match

    def test_rank_workflows(self, test_config):
        engine = SimilarityEngine(test_config)

        email_features = {
            "from_domain": "company.com",
            "subject_words": ["invoice", "payment"],
            "has_pdf": True,
            "body_preview_words": ["amount", "due"],
            "to": "user@example.com",
        }

        # Create some criteria instances
        criteria_instances = [
            CriteriaInstance(
                email_id="1",
                workflow_name="save-invoices",
                timestamp=datetime.now(),
                email_features={
                    "from_domain": "company.com",
                    "subject_words": ["invoice"],
                    "has_pdf": True,
                },
                confidence_score=0.9,
            ),
            CriteriaInstance(
                email_id="2",
                workflow_name="archive",
                timestamp=datetime.now() - timedelta(days=5),
                email_features={
                    "from_domain": "other.com",
                    "subject_words": ["newsletter"],
                    "has_pdf": False,
                },
                confidence_score=0.5,
            ),
            CriteriaInstance(
                email_id="3",
                workflow_name="save-invoices",
                timestamp=datetime.now() - timedelta(days=1),
                email_features={
                    "from_domain": "company.com",
                    "subject_words": ["receipt", "payment"],
                    "has_pdf": True,
                },
                confidence_score=0.85,
            ),
        ]

        rankings = engine.rank_workflows(email_features, criteria_instances, top_n=3)

        # Should rank save-invoices first due to high similarity
        assert len(rankings) > 0
        assert rankings[0][0] == "save-invoices"
        assert rankings[0][1] > 0.5  # Good confidence (adjusted threshold)
        assert len(rankings[0][2]) > 0  # Has matching instances

    def test_feature_explanation(self, test_config):
        engine = SimilarityEngine(test_config)

        email_features = {
            "from_domain": "example.com",
            "subject_words": ["invoice", "payment", "due"],
            "has_pdf": True,
        }

        criteria = CriteriaInstance(
            email_id="test1",
            workflow_name="archive",
            timestamp=datetime.now(),
            email_features={
                "from_domain": "example.com",
                "subject_words": ["invoice", "receipt"],
                "has_pdf": True,
            },
        )

        explanations = engine.get_feature_explanation(email_features, criteria)

        # Should explain matching features
        assert "from_domain" in explanations
        assert "example.com" in explanations["from_domain"]
        assert "subject" in explanations
        assert "invoice" in explanations["subject"]
        assert "attachments" in explanations
