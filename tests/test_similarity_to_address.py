from datetime import datetime

from mailflow.models import CriteriaInstance
from mailflow.similarity import SimilarityEngine
from mailflow.config import Config


def test_to_address_similarity_included(temp_config_dir):
    config = Config(config_dir=temp_config_dir)
    engine = SimilarityEngine(config)

    # Email features for current email
    email_features = {
        "from_domain": "example.com",
        "subject_words": {"invoice"},
        "body_preview_words": set(),
        "has_pdf": False,
        "to": "user@example.com",
    }

    # Criteria with same 'to' should score higher than different 'to'
    same_to = CriteriaInstance(
        email_id="1",
        workflow_name="wf-a",
        timestamp=datetime.now(),
        email_features={"to": "user@example.com"},
    )

    diff_to = CriteriaInstance(
        email_id="2",
        workflow_name="wf-b",
        timestamp=datetime.now(),
        email_features={"to": "other@example.com"},
    )

    score_same = engine.calculate_similarity(email_features, same_to)
    score_diff = engine.calculate_similarity(email_features, diff_to)

    assert score_same >= score_diff
