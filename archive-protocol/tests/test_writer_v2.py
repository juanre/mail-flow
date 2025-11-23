# ABOUTME: Tests for RepositoryWriter using layout v2 (docs/ + nested streams)

from datetime import datetime

from archive_protocol.config import RepositoryConfig
from archive_protocol.writer import RepositoryWriter


def test_write_document_v2_docs_dir(tmp_path):
    base = tmp_path / "archive"
    cfg = RepositoryConfig(base_path=str(base))
    writer = RepositoryWriter(cfg, entity="acme", source="mail", connector_version="1.0.0")

    created_at = datetime(2025, 11, 5, 12, 0, 0)
    _, content_path, _ = writer.write_document(
        workflow="invoices",
        content=b"PDF bytes",
        mimetype="application/pdf",
        origin={"message_id": "<x@y>"},
        created_at=created_at,
        original_filename="Invoice 1234.PDF",
    )

    # Path uses docs/{YYYY}/ with normalized filename
    assert "/acme/docs/2025/" in str(content_path)
    assert content_path.name.startswith("2025-11-05-invoice-1234")
    assert content_path.suffix == ".pdf"


def test_write_stream_v2_nested_stream(tmp_path):
    base = tmp_path / "archive"
    cfg = RepositoryConfig(base_path=str(base))
    writer = RepositoryWriter(cfg, entity="acme", source="slack", connector_version="1.0.0")

    created_at = datetime(2025, 11, 5, 9, 30, 0)
    _, content_path, _ = writer.write_stream(
        stream_name="slack/general",
        content=b"# Transcript\n",
        mimetype="text/markdown",
        origin={"workspace": "acme", "channel": "general"},
        created_at=created_at,
        original_filename="transcript.md",
    )

    # Nested stream path slack/general/{YYYY}
    assert "/acme/streams/slack/general/2025/" in str(content_path)
    assert content_path.name.startswith("2025-11-05-transcript")
    assert content_path.suffix == ".md"
