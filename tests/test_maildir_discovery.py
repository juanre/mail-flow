# ABOUTME: Tests for discovering Maildir and .eml files in fetch files.

from pathlib import Path

from mailflow.commands.gmail_batch_workflows import _discover_email_files


def test_discover_eml_recursive(tmp_path: Path):
    d = tmp_path / "a" / "b"
    d.mkdir(parents=True)
    f = d / "m1.eml"
    f.write_text("Subject: t\n\nbody", encoding="utf-8")
    out = _discover_email_files(tmp_path)
    assert f in out


def test_discover_maildir(tmp_path: Path):
    md = tmp_path / "INBOX" / "cur"
    md.mkdir(parents=True)
    f = md / "169999.mbox:2,S"
    f.write_text("From: a@b\nSubject: x\n\nbody", encoding="utf-8")
    out = _discover_email_files(tmp_path)
    assert f in out

