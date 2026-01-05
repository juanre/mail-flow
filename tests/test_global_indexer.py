from datetime import datetime
from pathlib import Path

from docflow_archive import RepositoryConfig, RepositoryWriter
from mailflow.indexer import run_indexer
from mailflow.global_index import GlobalIndex


def test_indexer_builds_global_indexes(tmp_path):
    base = tmp_path / "archive"
    cfg = RepositoryConfig(base_path=str(base))
    writer = RepositoryWriter(cfg, entity="acme", source="mail", connector_version="1.0.0")

    created_at = datetime(2025, 11, 5, 12, 0, 0)
    _, content_path, meta_path = writer.write_document(
        workflow="invoices",
        content=b"%PDF-1.4\n...",
        mimetype="application/pdf",
        origin={"message_id": "<x@y>", "subject": "Invoice 999", "from": "billing@vendor.com"},
        created_at=created_at,
        original_filename="Invoice-999.pdf",
    )

    assert content_path.exists() and meta_path.exists()

    # Build indexes
    count = run_indexer(str(base))
    assert count == 1

    # Search
    gi = GlobalIndex(str(base / "indexes"))
    results = list(gi.search("invoice", limit=5, entity="acme"))
    assert results and results[0]["filename"].endswith(".pdf")
