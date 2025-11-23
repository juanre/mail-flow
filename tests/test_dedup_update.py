from datetime import datetime

from mailflow.config import Config
from mailflow.processed_emails_tracker import ProcessedEmailsTracker


def test_processed_emails_preserves_first_message_id(temp_config_dir):
    cfg = Config(config_dir=temp_config_dir)
    tr = ProcessedEmailsTracker(cfg)

    content = "Subject: Test\n\nBody"
    mid1 = "<a@b>"
    mid2 = "<c@d>"

    tr.mark_as_processed(content, mid1, "wf1")
    assert tr.is_processed(content, mid1)

    # Mark same content with a different message id; should not overwrite existing message_id
    tr.mark_as_processed(content, mid2, "wf2")

    info = tr.get_processed_info(content, mid1)
    assert info is not None
    assert info["message_id"] == mid1

