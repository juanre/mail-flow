"""Integration tests for PDF extraction from real emails."""

from pathlib import Path

import pytest

from mailflow.attachment_handler import save_attachments_from_message
from mailflow.email_extractor import EmailExtractor
from mailflow.metadata_store import DocumentCategory, DocumentType, MetadataStore


class TestPDFExtractionIntegration:
    @pytest.fixture
    def cloudflare_email(self):
        """Load the Cloudflare invoice email with PDF attachment."""
        email_path = Path(__file__).parent / "res" / "cloudflare_invoice.eml"
        with open(email_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    @pytest.fixture
    def amazon_email(self):
        """Load the Amazon invoice email."""
        email_path = Path(__file__).parent / "res" / "amazon_invoice.eml"
        with open(email_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def test_extract_pdf_from_cloudflare_email(self, temp_config_dir, cloudflare_email):
        """Test extracting and saving PDF attachment from real Cloudflare email."""
        # Extract email data
        extractor = EmailExtractor()
        email_data = extractor.extract(cloudflare_email)

        # Verify email was parsed correctly
        assert "cloudflare.com" in email_data["from"]
        assert "cloudflare" in email_data["subject"].lower()
        assert email_data["_message_obj"] is not None

        # Check attachments were detected
        assert len(email_data["attachments"]) > 0
        pdf_attachments = [
            att for att in email_data["attachments"] if att["filename"].endswith(".pdf")
        ]
        assert len(pdf_attachments) == 1
        assert pdf_attachments[0]["filename"] == "cloudflare-invoice-2025-02-26.pdf"

        # Save the PDF attachment
        save_dir = Path(temp_config_dir) / "invoices"
        saved_count, failed_files = save_attachments_from_message(
            message_obj=email_data["_message_obj"],
            email_data=email_data,
            directory=str(save_dir),
            pattern="*.pdf",
            use_year_dirs=True,
            store_metadata=True,
        )

        assert saved_count == 1
        assert failed_files == []

        # Verify PDF was saved in year directory with date prefix
        year_dir = save_dir / "2025"  # Based on email date
        assert year_dir.exists()

        pdf_files = list(year_dir.glob("*.pdf"))
        assert len(pdf_files) == 1

        # Should have date prefix
        saved_pdf = pdf_files[0]
        assert saved_pdf.name.endswith("-cloudflare-invoice-2025-02-26.pdf")

        # Verify it's a valid PDF by checking header
        with open(saved_pdf, "rb") as f:
            header = f.read(4)
            assert header == b"%PDF"  # PDF magic number

        # Check metadata was stored
        store = MetadataStore(str(save_dir))
        results = store.get_by_message_id(email_data["message_id"])
        assert len(results) == 1

        metadata = results[0]
        assert metadata["filename"] == saved_pdf.name
        assert "cloudflare.com" in metadata["email_from"]
        assert metadata["pdf_type"] == "attachment"
        assert metadata["workflow_name"] == "save_attachment"

        # Check document classification
        assert metadata["document_type"] == DocumentType.INVOICE
        assert metadata["document_category"] == DocumentCategory.PURCHASE

    def test_pdf_extraction_with_document_info(self, temp_config_dir, cloudflare_email):
        """Test extracting PDF and storing document information."""
        # Extract email
        extractor = EmailExtractor()
        email_data = extractor.extract(cloudflare_email)

        # Add workflow info
        email_data["_workflow_name"] = "cloudflare-invoices"
        email_data["_confidence_score"] = 0.95

        # Save PDF
        save_dir = Path(temp_config_dir) / "cloudflare"
        saved_count, failed_files = save_attachments_from_message(
            message_obj=email_data["_message_obj"],
            email_data=email_data,
            directory=str(save_dir),
            pattern="*.pdf",
            store_metadata=True,
        )

        assert saved_count == 1
        assert failed_files == []

        # Update with extracted document info
        store = MetadataStore(str(save_dir))
        # Look in year subdirectory
        pdf_files = list(save_dir.glob("**/*.pdf"))

        store.update_document_info(
            message_id=email_data["message_id"],
            filename=pdf_files[0].name,
            document_info={
                "vendor": "Cloudflare",
                "invoice_date": "2025-02-26",
                "amount": 20.00,
                "currency": "USD",
                "service": "Cloudflare Pro",
            },
        )

        # Verify document info
        doc_info = store.get_document_info(email_data["message_id"], pdf_files[0].name)

        assert doc_info["document_type"] == DocumentType.INVOICE
        assert doc_info["info"]["vendor"] == "Cloudflare"
        assert doc_info["info"]["amount"] == 20.00

    def test_no_pdf_attachment_creates_pdf(self, temp_config_dir, amazon_email):
        """Test that emails without PDF attachments can be converted to PDF."""
        from mailflow.pdf_converter import save_email_as_pdf

        # Extract email
        extractor = EmailExtractor()
        email_data = extractor.extract(amazon_email)

        # Check no PDF attachments
        pdf_attachments = [
            att for att in email_data.get("attachments", []) if att["filename"].endswith(".pdf")
        ]
        assert len(pdf_attachments) == 0

        # Convert email to PDF
        save_dir = Path(temp_config_dir) / "receipts"
        save_email_as_pdf(
            email_data=email_data,
            message_obj=email_data.get("_message_obj"),
            directory=str(save_dir),
            filename_template="amazon-aws-bill",
            store_metadata=True,
        )

        # Verify PDF was created (in year subdirectory)
        pdf_files = list(save_dir.glob("**/*.pdf"))
        assert len(pdf_files) == 1
        assert "amazon-aws-bill" in pdf_files[0].name

        # Check metadata
        store = MetadataStore(str(save_dir))
        results = store.get_by_message_id(email_data["message_id"])
        assert len(results) == 1

        metadata = results[0]
        assert metadata["pdf_type"] == "converted"
        # Amazon AWS bills are classified as invoices
        assert metadata["document_type"] == DocumentType.INVOICE
        assert metadata["document_category"] == DocumentCategory.PURCHASE

    def test_search_extracted_pdfs(self, temp_config_dir, cloudflare_email):
        """Test searching through extracted PDFs."""
        # Extract and save
        extractor = EmailExtractor()
        email_data = extractor.extract(cloudflare_email)

        save_dir = Path(temp_config_dir) / "all-invoices"
        saved_count, failed_files = save_attachments_from_message(
            message_obj=email_data["_message_obj"],
            email_data=email_data,
            directory=str(save_dir),
            pattern="*.pdf",
            store_metadata=True,
        )
        assert saved_count == 1
        assert failed_files == []

        # Search
        store = MetadataStore(str(save_dir))

        # Search by content
        results = store.search("cloudflare")
        assert len(results) == 1
        assert "cloudflare.com" in results[0]["email_from"]

        # Search by document type
        invoices = store.search_by_type(DocumentType.INVOICE)
        assert len(invoices) == 1

        # Get statistics
        stats = store.get_statistics()
        assert stats["total_pdfs"] == 1
        assert stats["by_pdf_type"]["attachment"] == 1
        assert stats["by_document_type"][DocumentType.INVOICE] == 1
