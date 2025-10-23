"""Test metadata storage functionality."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from mailflow.exceptions import DataError
from mailflow.metadata_store import MetadataStore


class TestMetadataStore:
    def test_init_creates_database(self, temp_config_dir):
        """Test that database is created on initialization."""
        store = MetadataStore(temp_config_dir)

        db_path = Path(temp_config_dir) / f"{Path(temp_config_dir).name}.db"
        assert db_path.exists()

    def test_store_pdf_metadata(self, temp_config_dir):
        """Test storing PDF metadata."""
        store = MetadataStore(temp_config_dir)

        # Create a fake PDF
        pdf_path = Path(temp_config_dir) / "2024" / "2024-01-15-test.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_text("fake pdf content")

        # Email data
        email_data = {
            "message_id": "<test-123@example.com>",
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "subject": "Test Invoice",
            "date": "Mon, 15 Jan 2024 10:00:00 +0000",
            "body": "This is a test invoice email",
            "attachments": [],
            "features": {"from_domain": "example.com"},
        }

        # Store metadata
        store.store_pdf_metadata(
            pdf_path=pdf_path,
            email_data=email_data,
            workflow_name="test-workflow",
            pdf_type="converted",
            confidence_score=0.85,
        )

        # Verify stored
        results = store.get_by_message_id("<test-123@example.com>")
        assert len(results) == 1
        assert results[0]["filename"] == "2024-01-15-test.pdf"
        assert results[0]["workflow_name"] == "test-workflow"
        assert results[0]["confidence_score"] == 0.85

    def test_search_functionality(self, temp_config_dir):
        """Test searching PDFs."""
        store = MetadataStore(temp_config_dir)

        # Store multiple PDFs
        for i, (subject, sender) in enumerate(
            [
                ("Amazon Invoice #123", "billing@amazon.com"),
                ("Utility Bill January", "service@utility.com"),
                ("Amazon Order Confirmation", "orders@amazon.com"),
            ]
        ):
            pdf_path = Path(temp_config_dir) / f"test-{i}.pdf"
            pdf_path.write_text("fake")

            store.store_pdf_metadata(
                pdf_path=pdf_path,
                email_data={
                    "message_id": f"<msg-{i}@example.com>",
                    "from": sender,
                    "subject": subject,
                    "body": f"Email body {i}",
                    "date": "Mon, 15 Jan 2024 10:00:00 +0000",
                },
                workflow_name="test",
                pdf_type="attachment",
            )

        # Search for amazon
        results = store.search("amazon")
        assert len(results) == 2

        # Search for invoice
        results = store.search("invoice")
        assert len(results) == 1
        assert "Amazon Invoice" in results[0]["email_subject"]

    def test_duplicate_check(self, temp_config_dir):
        """Test duplicate detection."""
        store = MetadataStore(temp_config_dir)

        pdf_path = Path(temp_config_dir) / "test.pdf"
        pdf_path.write_text("fake")

        email_data = {
            "message_id": "<dup-test@example.com>",
            "from": "test@example.com",
            "subject": "Test",
            "body": "Test",
            "date": "Mon, 15 Jan 2024 10:00:00 +0000",
        }

        # Store once
        store.store_pdf_metadata(
            pdf_path=pdf_path, email_data=email_data, workflow_name="test", pdf_type="attachment"
        )

        # Check duplicate
        assert store.check_duplicate("<dup-test@example.com>", "test.pdf")
        assert not store.check_duplicate("<other@example.com>", "test.pdf")

    def test_statistics(self, temp_config_dir):
        """Test statistics generation."""
        store = MetadataStore(temp_config_dir)

        # Store PDFs with different attributes
        for i in range(5):
            pdf_path = Path(temp_config_dir) / f"test-{i}.pdf"
            pdf_path.write_text("x" * 1000)  # 1KB each

            store.store_pdf_metadata(
                pdf_path=pdf_path,
                email_data={
                    "message_id": f"<stat-{i}@example.com>",
                    "from": "test@example.com",
                    "subject": f"Test {i}",
                    "body": "Test",
                    "date": f"Mon, 15 Jan 202{i} 10:00:00 +0000",
                },
                workflow_name="workflow1" if i < 3 else "workflow2",
                pdf_type="attachment" if i % 2 == 0 else "converted",
            )

        stats = store.get_statistics()

        assert stats["total_pdfs"] == 5
        assert stats["total_size_mb"] < 1.0  # Should be ~5KB
        assert stats["by_pdf_type"]["attachment"] == 3
        assert stats["by_pdf_type"]["converted"] == 2
        assert stats["by_workflow"]["workflow1"] == 3
        assert stats["by_workflow"]["workflow2"] == 2

    def test_text_extraction_from_html(self, temp_config_dir):
        """Test HTML to text extraction."""
        store = MetadataStore(temp_config_dir)

        html_body = """
        <html>
        <body>
            <h1>Invoice</h1>
            <p>Total: $100.00</p>
            <script>alert('test')</script>
        </body>
        </html>
        """

        text = store._extract_text_from_body(html_body)
        assert "Invoice" in text
        assert "Total: $100.00" in text
        assert "script" not in text
        assert "alert" not in text
