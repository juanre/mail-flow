# ABOUTME: Tests for expense export functionality
# ABOUTME: Tests expenses.csv and xero-bills.csv export from archive sidecars

import csv
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture
def archive_with_expense(tmp_path):
    """Create a minimal archive directory with one doc+sidecar containing expense data.

    Structure:
        tmp_path/
            tsm/
                docs/
                    2025/
                        2025-12-15-mail-xyz.pdf
                        2025-12-15-mail-xyz.json  (sidecar with accounting.expense)
    """
    # Create directory structure
    entity = "tsm"
    docs_dir = tmp_path / entity / "docs" / "2025"
    docs_dir.mkdir(parents=True)

    # Create dummy PDF content
    content_path = docs_dir / "2025-12-15-mail-abc123.pdf"
    content_path.write_bytes(b"%PDF-1.4 fake pdf content")

    # Create sidecar JSON with accounting.expense
    sidecar_path = docs_dir / "2025-12-15-mail-abc123.json"
    sidecar_data = {
        "id": "mail=tsm-expense/2025-12-15T10:30:00Z/sha256:abc123def456" + "0" * 52,
        "entity": "tsm",
        "source": "mail",
        "workflow": "tsm-expense",
        "type": "document",
        "subtype": None,
        "created_at": "2025-12-15T10:30:00+00:00",
        "content": {
            "path": "2025-12-15-mail-abc123.pdf",
            "hash": "sha256:abc123def456" + "0" * 52,
            "size_bytes": 1024,
            "mimetype": "application/pdf",
            "attachments": []
        },
        "origin": {
            "message_id": "<expense123@vendor.com>",
            "subject": "Invoice #12345",
            "from": "billing@acme-vendor.com",
            "to": "expenses@tsm.com",
            "date": "Sun, 15 Dec 2025 10:30:00 +0000"
        },
        "tags": ["expense"],
        "relationships": [],
        "ingest": {
            "connector": "mail@1.0.0",
            "ingested_at": "2025-12-15T10:35:00+00:00",
            "hostname": "test-host"
        },
        "llmemory": {
            "indexed_at": None,
            "document_id": None,
            "chunks_created": None,
            "embedding_model": None
        },
        "accounting": {
            "expense": {
                "expense_date": "2025-12-15",
                "vendor": "ACME Vendor Inc",
                "total_amount": "299.99",
                "currency": "USD",
                "category": "software",
                "tax_amount": "24.99",
                "invoice_number": "INV-12345",
                "payment_method": "card",
                "cost_center": None,
                "memo": "Annual subscription renewal",
                "source_document_id": "mail=tsm-expense/2025-12-15T10:30:00Z/sha256:abc123def456" + "0" * 52,
                "source_path": "tsm/docs/2025/2025-12-15-mail-abc123.pdf",
                "extracted_at": "2025-12-15T10:40:00+00:00",
                "extractor": "mailflow-expense@0.1.0"
            }
        }
    }
    sidecar_path.write_text(json.dumps(sidecar_data, indent=2))

    return tmp_path, sidecar_data


class TestExpenseExport:
    """Test expense export functionality."""

    def test_expenses_csv_export_single_document(self, archive_with_expense):
        """Test exporting a single expense document to CSV."""
        archive_path, sidecar_data = archive_with_expense

        from mailflow.expense_export import export_expenses_csv

        output = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        output.close()
        output_path = Path(output.name)

        try:
            export_expenses_csv(
                archive_path=archive_path,
                output_path=output_path,
                entity="tsm"
            )

            # Read and verify CSV
            with open(output_path, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 1
            row = rows[0]

            # Required columns per SOT
            assert row['entity'] == 'tsm'
            assert row['workflow'] == 'tsm-expense'
            assert row['expense_date'] == '2025-12-15'
            assert row['vendor'] == 'ACME Vendor Inc'
            assert row['total_amount'] == '299.99'
            assert row['currency'] == 'USD'
            assert 'document_id' in row
            assert 'archive_path' in row

            # Traceability - these must point to the actual archived file
            assert 'sha256:abc123def456' in row['document_id']
            assert 'tsm/docs/2025/2025-12-15-mail-abc123.pdf' in row['archive_path']

            # Recommended columns
            assert row.get('tax_amount') == '24.99'
            assert row.get('invoice_number') == 'INV-12345'
            assert row.get('category') == 'software'
            assert row.get('source') == 'mail'
        finally:
            output_path.unlink(missing_ok=True)

    def test_expenses_csv_export_empty_archive(self, tmp_path):
        """Test export with no expense documents."""
        from mailflow.expense_export import export_expenses_csv

        output = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        output.close()
        output_path = Path(output.name)

        try:
            export_expenses_csv(
                archive_path=tmp_path,
                output_path=output_path,
                entity="tsm"
            )

            # Should produce empty CSV with headers only
            with open(output_path, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 0
            # But headers should still be present
            with open(output_path, 'r') as f:
                header_line = f.readline()
            assert 'entity' in header_line
            assert 'document_id' in header_line
        finally:
            output_path.unlink(missing_ok=True)

    def test_expenses_csv_idempotent(self, archive_with_expense):
        """Test that export is idempotent (same archive state = same output)."""
        archive_path, _ = archive_with_expense

        from mailflow.expense_export import export_expenses_csv

        output1 = Path(tempfile.mktemp(suffix='.csv'))
        output2 = Path(tempfile.mktemp(suffix='.csv'))

        try:
            export_expenses_csv(archive_path=archive_path, output_path=output1, entity="tsm")
            export_expenses_csv(archive_path=archive_path, output_path=output2, entity="tsm")

            # Both outputs should be identical
            assert output1.read_text() == output2.read_text()
        finally:
            output1.unlink(missing_ok=True)
            output2.unlink(missing_ok=True)


class TestXeroBillsExport:
    """Test Xero bills CSV export functionality."""

    def test_xero_bills_csv_export(self, archive_with_expense):
        """Test exporting expenses as Xero-compatible bills CSV."""
        archive_path, sidecar_data = archive_with_expense

        from mailflow.expense_export import export_xero_bills_csv

        output = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        output.close()
        output_path = Path(output.name)

        try:
            export_xero_bills_csv(
                archive_path=archive_path,
                output_path=output_path,
                entity="tsm"
            )

            # Read and verify CSV
            with open(output_path, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 1
            row = rows[0]

            # Xero-specific columns per SOT
            assert row['ContactName'] == 'ACME Vendor Inc'
            assert row['InvoiceNumber'] == 'INV-12345'
            assert row['InvoiceDate'] == '2025-12-15'
            assert row['Quantity'] == '1'
            assert row['UnitAmount'] == '299.99'

            # Traceability requirements per SOT:
            # - Reference MUST include document_id
            # - Description MUST include archive_path
            assert 'archive:' in row['Reference']
            assert 'sha256:abc123def456' in row['Reference']
            assert 'tsm/docs/2025/2025-12-15-mail-abc123.pdf' in row['Description']
        finally:
            output_path.unlink(missing_ok=True)


class TestExpenseValidation:
    """Test expense data validation."""

    def test_expenses_csv_skips_missing_required_fields(self, tmp_path):
        """Test that sidecars with missing required fields are skipped."""
        # Create directory structure
        docs_dir = tmp_path / "tsm" / "docs" / "2025"
        docs_dir.mkdir(parents=True)

        # Create sidecar with expense but missing vendor field
        sidecar_path = docs_dir / "incomplete.json"
        sidecar_data = {
            "id": "mail=tsm-expense/2025-12-15T10:30:00Z/sha256:incomplete",
            "entity": "tsm",
            "source": "mail",
            "workflow": "tsm-expense",
            "accounting": {
                "expense": {
                    "expense_date": "2025-12-15",
                    # vendor is missing!
                    "total_amount": "100.00",
                    "currency": "USD",
                    "category": "software"
                }
            }
        }
        sidecar_path.write_text(json.dumps(sidecar_data))

        from mailflow.expense_export import export_expenses_csv

        output_path = tmp_path / "output.csv"
        count = export_expenses_csv(
            archive_path=tmp_path,
            output_path=output_path,
            entity="tsm"
        )

        # Should skip the invalid expense
        assert count == 0

        # CSV should have headers only
        with open(output_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 0

    def test_expenses_csv_exports_valid_skips_invalid(self, tmp_path):
        """Test export with mix of valid and invalid sidecars."""
        docs_dir = tmp_path / "tsm" / "docs" / "2025"
        docs_dir.mkdir(parents=True)

        # Create valid sidecar
        valid_sidecar = docs_dir / "valid.json"
        valid_sidecar.write_text(json.dumps({
            "id": "mail=tsm-expense/2025-12-15T10:30:00Z/sha256:valid",
            "entity": "tsm",
            "source": "mail",
            "workflow": "tsm-expense",
            "accounting": {
                "expense": {
                    "expense_date": "2025-12-15",
                    "vendor": "Valid Vendor",
                    "total_amount": "100.00",
                    "currency": "USD",
                    "category": "software",
                    "source_path": "tsm/docs/2025/valid.pdf"
                }
            }
        }))

        # Create invalid sidecar (missing currency)
        invalid_sidecar = docs_dir / "invalid.json"
        invalid_sidecar.write_text(json.dumps({
            "id": "mail=tsm-expense/2025-12-15T10:30:00Z/sha256:invalid",
            "entity": "tsm",
            "source": "mail",
            "workflow": "tsm-expense",
            "accounting": {
                "expense": {
                    "expense_date": "2025-12-15",
                    "vendor": "Invalid Vendor",
                    "total_amount": "50.00",
                    # currency is missing!
                    "category": "software"
                }
            }
        }))

        from mailflow.expense_export import export_expenses_csv

        output_path = tmp_path / "output.csv"
        count = export_expenses_csv(
            archive_path=tmp_path,
            output_path=output_path,
            entity="tsm"
        )

        # Should export only the valid expense
        assert count == 1

        with open(output_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]['vendor'] == 'Valid Vendor'

    def test_malformed_json_is_skipped(self, tmp_path):
        """Test that malformed JSON files are logged and skipped."""
        docs_dir = tmp_path / "tsm" / "docs" / "2025"
        docs_dir.mkdir(parents=True)

        # Create valid sidecar
        valid_sidecar = docs_dir / "valid.json"
        valid_sidecar.write_text(json.dumps({
            "id": "mail=tsm-expense/2025-12-15T10:30:00Z/sha256:valid",
            "entity": "tsm",
            "source": "mail",
            "workflow": "tsm-expense",
            "accounting": {
                "expense": {
                    "expense_date": "2025-12-15",
                    "vendor": "Valid Vendor",
                    "total_amount": "100.00",
                    "currency": "USD",
                    "source_path": "tsm/docs/2025/valid.pdf"
                }
            }
        }))

        # Create malformed JSON file
        malformed = docs_dir / "malformed.json"
        malformed.write_text("{ this is not valid json }")

        from mailflow.expense_export import export_expenses_csv

        output_path = tmp_path / "output.csv"
        count = export_expenses_csv(
            archive_path=tmp_path,
            output_path=output_path,
            entity="tsm"
        )

        # Should export only the valid expense (malformed skipped)
        assert count == 1
