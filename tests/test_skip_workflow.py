# ABOUTME: Tests for skip workflow handling (negative training examples).
"""Tests for skip workflow handling."""

from mailflow.config import Config
from mailflow.models import DataStore


class TestSkipWorkflow:
    def test_skip_recorded_as_criteria_instance(self, temp_config_dir):
        config = Config(config_dir=temp_config_dir)
        data_store = DataStore(config)

        email_id = "<skip-test-1@example.com>"
        features = {"from_domain": "newsletter.com", "subject_tokens": ["weekly", "digest"]}

        data_store.record_skip(email_id, features)

        # Check it was recorded
        instances = data_store.get_recent_criteria()
        skip_instances = [i for i in instances if i.workflow_name == "_skip"]
        assert len(skip_instances) == 1
        assert skip_instances[0].email_features["from_domain"] == "newsletter.com"

    def test_skip_workflow_not_in_user_workflows(self, temp_config_dir):
        config = Config(config_dir=temp_config_dir)
        data_store = DataStore(config)

        # _skip should not appear in workflow list (it's internal)
        assert "_skip" not in data_store.workflows
