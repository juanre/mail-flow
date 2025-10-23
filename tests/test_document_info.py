"""Test document info and classification functionality."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from mailflow.exceptions import DataError
from mailflow.metadata_store import DocumentCategory, DocumentType, MetadataStore


class TestDocumentInfo:
    def test_store_with_document_classification(self, temp_config_dir):
        """Test storing PDF with document type and category."""
        store = MetadataStore(temp_config_dir)

        # Create a fake PDF
        pdf_path = Path(temp_config_dir) / "2024-01-15-invoice.pdf"
        pdf_path.write_text("fake pdf content")

        # Email data
        email_data = {
            "message_id": "<invoice-123@example.com>",
            "from": "billing@amazon.com",
            "to": "customer@example.com",
            "subject": "Invoice #INV-2024-001",
            "date": "Mon, 15 Jan 2024 10:00:00 +0000",
            "body": "Your invoice for order #12345",
        }

        # Document info
        document_info = {
            "amount": 99.99,
            "currency": "USD",
            "vendor": "Amazon",
            "invoice_number": "INV-2024-001",
            "invoice_date": "2024-01-15",
            "items": [{"description": "Widget", "quantity": 2, "price": 49.99}],
        }

        # Store with classification
        store.store_pdf_metadata(
            pdf_path=pdf_path,
            email_data=email_data,
            workflow_name="invoices",
            pdf_type="attachment",
            document_type=DocumentType.INVOICE,
            document_category=DocumentCategory.PURCHASE,
            document_info=document_info,
        )

        # Verify stored correctly
        results = store.get_by_message_id("<invoice-123@example.com>")
        assert len(results) == 1

        result = results[0]
        assert result["document_type"] == DocumentType.INVOICE
        assert result["document_category"] == DocumentCategory.PURCHASE

        # Check document info
        stored_info = json.loads(result["document_info"])
        assert stored_info["amount"] == 99.99
        assert stored_info["vendor"] == "Amazon"
        assert stored_info["invoice_number"] == "INV-2024-001"

    def test_update_document_classification(self, temp_config_dir):
        """Test updating document classification after storing."""
        store = MetadataStore(temp_config_dir)

        # Create and store a PDF without classification
        pdf_path = Path(temp_config_dir) / "2024-01-15-document.pdf"
        pdf_path.write_text("fake pdf")

        email_data = {
            "message_id": "<doc-456@example.com>",
            "from": "sender@example.com",
            "subject": "Document",
            "date": "Mon, 15 Jan 2024 10:00:00 +0000",
        }

        store.store_pdf_metadata(pdf_path=pdf_path, email_data=email_data, workflow_name="general")

        # Update classification
        store.update_document_classification(
            message_id="<doc-456@example.com>",
            filename="2024-01-15-document.pdf",
            document_type=DocumentType.RECEIPT,
            document_category=DocumentCategory.EXPENSE,
        )

        # Verify update
        results = store.get_by_message_id("<doc-456@example.com>")
        assert results[0]["document_type"] == DocumentType.RECEIPT
        assert results[0]["document_category"] == DocumentCategory.EXPENSE

    def test_update_document_info(self, temp_config_dir):
        """Test updating document info incrementally."""
        store = MetadataStore(temp_config_dir)

        # Create and store a PDF
        pdf_path = Path(temp_config_dir) / "2024-01-15-receipt.pdf"
        pdf_path.write_text("fake pdf")

        email_data = {
            "message_id": "<receipt-789@example.com>",
            "from": "store@example.com",
            "subject": "Receipt",
            "date": "Mon, 15 Jan 2024 10:00:00 +0000",
        }

        # Store with initial info
        store.store_pdf_metadata(
            pdf_path=pdf_path,
            email_data=email_data,
            workflow_name="receipts",
            document_info={"amount": 50.00},
        )

        # Update with more info
        store.update_document_info(
            message_id="<receipt-789@example.com>",
            filename="2024-01-15-receipt.pdf",
            document_info={
                "vendor": "Example Store",
                "payment_method": "Credit Card",
                "tax_amount": 4.50,
            },
        )

        # Get document info
        doc_info = store.get_document_info("<receipt-789@example.com>", "2024-01-15-receipt.pdf")

        assert doc_info is not None
        assert doc_info["info"]["amount"] == 50.00
        assert doc_info["info"]["vendor"] == "Example Store"
        assert doc_info["info"]["tax_amount"] == 4.50

    def test_search_by_document_type(self, temp_config_dir):
        """Test searching by document type."""
        store = MetadataStore(temp_config_dir)

        # Store multiple PDFs with different types
        for i, (doc_type, vendor) in enumerate(
            [
                ("invoice", "Amazon"),
                ("receipt", "Walmart"),
                ("invoice", "Apple"),
                ("statement", "Bank"),
                ("receipt", "Target"),
            ]
        ):
            pdf_path = Path(temp_config_dir) / f"doc-{i}.pdf"
            pdf_path.write_text("fake")

            store.store_pdf_metadata(
                pdf_path=pdf_path,
                email_data={
                    "message_id": f"<msg-{i}@example.com>",
                    "from": f"{vendor.lower()}@example.com",
                    "subject": f"{doc_type} from {vendor}",
                    "date": "Mon, 15 Jan 2024 10:00:00 +0000",
                },
                workflow_name="test",
                document_type=doc_type,
                document_info={"vendor": vendor},
            )

        # Search for invoices
        invoices = store.search_by_type("invoice")
        assert len(invoices) == 2
        assert all(r["document_type"] == "invoice" for r in invoices)

        # Search for receipts
        receipts = store.search_by_type("receipt")
        assert len(receipts) == 2
        assert all(r["document_type"] == "receipt" for r in receipts)

    def test_statistics_with_document_types(self, temp_config_dir):
        """Test statistics include document types."""
        store = MetadataStore(temp_config_dir)

        # Store PDFs with various classifications
        classifications = [
            ("invoice", "purchase"),
            ("invoice", "purchase"),
            ("receipt", "expense"),
            ("tax", "government"),
            ("statement", "financial"),
            ("receipt", "expense"),
        ]

        for i, (doc_type, category) in enumerate(classifications):
            pdf_path = Path(temp_config_dir) / f"doc-{i}.pdf"
            pdf_path.write_text("fake")

            store.store_pdf_metadata(
                pdf_path=pdf_path,
                email_data={
                    "message_id": f"<stat-{i}@example.com>",
                    "from": "sender@example.com",
                    "subject": f"{doc_type} document",
                    "date": "Mon, 15 Jan 2024 10:00:00 +0000",
                },
                workflow_name="test",
                document_type=doc_type,
                document_category=category,
            )

        stats = store.get_statistics()

        # Check document type stats
        assert stats["by_document_type"]["invoice"] == 2
        assert stats["by_document_type"]["receipt"] == 2
        assert stats["by_document_type"]["tax"] == 1
        assert stats["by_document_type"]["statement"] == 1

        # Check category stats
        assert stats["by_category"]["purchase"] == 2
        assert stats["by_category"]["expense"] == 2
        assert stats["by_category"]["government"] == 1
        assert stats["by_category"]["financial"] == 1

    def test_document_classification_suggestion(self):
        """Test automatic document classification based on email content."""
        # Invoice email
        invoice_email = {
            "subject": "Invoice #12345 - Payment Due",
            "from": "billing@company.com",
            "body": "Please pay the attached invoice by the due date.",
        }
        doc_type, doc_cat = MetadataStore.suggest_document_classification(invoice_email)
        assert doc_type == DocumentType.INVOICE
        assert doc_cat == DocumentCategory.PURCHASE

        # Receipt email
        receipt_email = {
            "subject": "Your order confirmation",
            "from": "orders@store.com",
            "body": "Thank you for your order! Here's your receipt.",
        }
        doc_type, doc_cat = MetadataStore.suggest_document_classification(receipt_email)
        assert doc_type == DocumentType.RECEIPT
        assert doc_cat == DocumentCategory.PURCHASE

        # Tax document
        tax_email = {
            "subject": "Your 1099 form is ready",
            "from": "tax@company.com",
            "body": "Your tax documents are available.",
        }
        doc_type, doc_cat = MetadataStore.suggest_document_classification(tax_email)
        assert doc_type == DocumentType.TAX
        assert doc_cat == DocumentCategory.GOVERNMENT

        # Unknown document
        unknown_email = {"subject": "Hello", "from": "friend@example.com", "body": "How are you?"}
        doc_type, doc_cat = MetadataStore.suggest_document_classification(unknown_email)
        assert doc_type == DocumentType.UNKNOWN
        assert doc_cat == DocumentCategory.UNCATEGORIZED
