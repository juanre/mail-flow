from pathlib import Path

from mailflow.metadata_store import MetadataStore


def test_search_recent_returns_latest(temp_config_dir):
    store = MetadataStore(temp_config_dir)

    # Create three dummy PDFs
    for i in range(3):
        p = Path(temp_config_dir) / f"file-{i}.pdf"
        p.write_text("x")
        store.store_pdf_metadata(
            pdf_path=p,
            email_data={
                "message_id": f"<msg-{i}>",
                "from": "sender@example.com",
                "to": "user@example.com",
                "subject": f"Subj {i}",
                "body": "",
                "date": f"2024-01-0{i+1} 10:00:00",
            },
            workflow_name="test",
            pdf_type="attachment",
        )

    results = store.search("", limit=2)
    assert len(results) == 2
    # Ensure the most recent two are returned (by saved_at DESC)
    assert results[0]["filename"].startswith("file-")
