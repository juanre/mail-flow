import json
from pathlib import Path
from datetime import datetime

import pytest

from mailflow.config import Config
from mailflow.slack import ingest as slack_ingest
from mailflow.slack.storage import SlackArchivePaths
from mailflow.slack.migrate_contextual import migrate_contextual_slack
from mailflow.gdocs import ingest as gdocs_ingest


class FakeSlackClient:
    def __init__(self, *args, **kwargs):
        self._domain = "example"

    def team_domain(self) -> str:
        return self._domain

    def users_map(self):
        return {"U1": "alice", "U2": "bob"}

    def history(self, channel_id: str, oldest=None):
        # one parent message with attachment, one plain message
        yield {
            "ts": "1000.000001",
            "user": "U1",
            "text": "hello <@U2>",
            "thread_ts": "1000.000001",
            "files": [
                {
                    "id": "F123",
                    "title": "readme",
                    "name": "readme.txt",
                    "mimetype": "text/plain",
                    "timestamp": 1000.0,
                    "url_private_download": "https://files.local/F123",
                    "permalink": "https://example.slack.com/files/F123",
                }
            ],
        }
        yield {"ts": "1001.000001", "user": "U2", "text": "replying"}

    def replies(self, channel_id: str, thread_ts: str):
        return [{"ts": "1000.000002", "user": "U2", "text": "hi back"}]

    def download_private_url(self, url: str, dest: Path):
        # write a small text file
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("attachment content", encoding="utf-8")


def _temp_config(tmp_path: Path) -> Config:
    cfg = Config(config_dir=str(tmp_path / ".mailflow-test"))
    # Set base dirs to tmp
    cfg.settings.setdefault("slack", {})
    cfg.settings["slack"]["base_dir"] = str(tmp_path / "slack-archive")
    cfg.settings.setdefault("gdocs", {})
    cfg.settings["gdocs"]["base_dir"] = str(tmp_path / "gdocs-archive")
    # Keep llmemory disabled by default for unit tests
    cfg.settings.setdefault("llmemory", {"enabled": False})
    cfg.save_config()
    return cfg


def test_slack_ingest_happy_path(tmp_path, monkeypatch):
    cfg = _temp_config(tmp_path)

    # Monkeypatch SlackClient in ingest to FakeSlackClient
    monkeypatch.setattr(slack_ingest, "SlackClient", FakeSlackClient)

    # Create a dummy token file to satisfy constructor path checks
    token_file = tmp_path / ".mailflow-test" / "slack" / "ent" / "user_token"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text("xoxp-TEST", encoding="utf-8")

    # Ingest
    count = slack_ingest.ingest_channel(cfg, "ent", "C123", "general", None, False)
    assert count > 0

    # Check outputs
    paths = SlackArchivePaths(cfg.settings["slack"]["base_dir"], "ent", "general")
    # Any md/json created for the day present in messages (ts 1000 -> 1970-01-01)
    md_files = list(paths.md_dir.glob("*.md"))
    json_files = list(paths.raw_dir.glob("*.json"))
    assert md_files and json_files
    md_text = md_files[0].read_text(encoding="utf-8")
    assert "@bob" in md_text  # mention replaced
    assert "Attachments" in md_text
    # Attachment presence
    att_files = list(paths.attach_dir.glob("*.txt"))
    assert att_files and att_files[0].read_text(encoding="utf-8") == "attachment content"


def test_slack_migration_org_to_md(tmp_path):
    cfg = _temp_config(tmp_path)
    old_root = tmp_path / "old"
    org_dir = old_root / "slack"
    raw_dir = old_root / "raw" / "slack"
    att_dir = raw_dir / "attachments"
    org_dir.mkdir(parents=True, exist_ok=True)
    att_dir.mkdir(parents=True, exist_ok=True)

    # Create attachment source
    (att_dir / "general").mkdir(parents=True, exist_ok=True)
    src_file = att_dir / "general" / "readme.txt"
    src_file.write_text("old attachment", encoding="utf-8")

    # Create raw json for the date
    date_str = "2020-01-02"
    (raw_dir / "general").parent.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{date_str}-general.json").write_text("[]", encoding="utf-8")

    # Create org file with a file link
    org = org_dir / f"{date_str}-general.org"
    org.write_text(
        """
* alice
:PROPERTIES:
:SLACK_LINK: https://example.slack.com/archives/general/p1000
:END:

** Attachments
*** [[file:attachments/general/readme.txt][readme]]
""".strip(),
        encoding="utf-8",
    )

    count = migrate_contextual_slack(str(old_root), "ent", cfg)
    assert count == 1

    new_md_dir = Path(cfg.settings["slack"]["base_dir"]) / "ent" / "md" / "general"
    new_md = next(new_md_dir.glob("*.md"))
    text = new_md.read_text(encoding="utf-8")
    assert "Permalink:" in text and "readme" in text


class FakeGoogleClient:
    def __init__(self):
        pass

    def file_metadata(self, file_id: str):
        return {"name": "Test Doc", "modifiedTime": "2025-01-01T12:00:00Z"}

    def export_markdown(self, file_id: str) -> bytes:
        return b"# Title\n\nBody"

    def export_pdf(self, file_id: str) -> bytes:
        return b"%PDF-1.4\n%..."


def test_gdocs_ingest_id(tmp_path, monkeypatch):
    cfg = _temp_config(tmp_path)
    # Monkeypatch GoogleClient to avoid network
    monkeypatch.setattr(gdocs_ingest, "GoogleClient", FakeGoogleClient)

    md, pdf = gdocs_ingest.ingest_doc_id(cfg, "ent", "FILEID")
    assert md.exists() and pdf.exists()
    assert md.read_text(encoding="utf-8").startswith("# Title")


