# ABOUTME: Expense export functionality for mailflow
# ABOUTME: Exports expenses.csv and xero-bills.csv from archive sidecars

import csv
import json
import logging
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

# Required columns for expenses.csv per SOT
EXPENSES_CSV_COLUMNS = [
    "entity",
    "workflow",
    "expense_date",
    "vendor",
    "total_amount",
    "currency",
    "document_id",
    "archive_path",
    # Recommended columns
    "tax_amount",
    "invoice_number",
    "payment_method",
    "category",
    "cost_center",
    "memo",
    "source",
    "origin_id",
    "created_at",
]

# Xero bills CSV columns per SOT
XERO_BILLS_COLUMNS = [
    "ContactName",
    "InvoiceNumber",
    "InvoiceDate",
    "DueDate",
    "Description",
    "Quantity",
    "UnitAmount",
    "AccountCode",
    "TaxType",
    "Reference",
]


def find_sidecars_with_expenses(archive_path: Path, entity: str | None = None) -> Iterator[tuple[Path, dict]]:
    """Find all sidecar JSON files containing accounting.expense data.

    Args:
        archive_path: Root path of the archive
        entity: Optional entity filter (e.g., "tsm")

    Yields:
        Tuples of (sidecar_path, sidecar_data) for files with expense data
    """
    search_path = archive_path
    if entity:
        search_path = archive_path / entity

    if not search_path.exists():
        return

    for sidecar_path in search_path.rglob("*.json"):
        try:
            with open(sidecar_path, "r") as f:
                data = json.load(f)

            # Check if this sidecar has accounting.expense data
            if data.get("accounting", {}).get("expense"):
                yield sidecar_path, data
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to read sidecar {sidecar_path}: {e}")
            continue


def sidecar_to_expense_row(sidecar_data: dict, archive_path: Path) -> dict:
    """Convert a sidecar with expense data to an expenses.csv row.

    Args:
        sidecar_data: Parsed sidecar JSON
        archive_path: Root archive path for computing relative paths

    Returns:
        Dictionary with expenses.csv column values
    """
    expense = sidecar_data.get("accounting", {}).get("expense", {})
    origin = sidecar_data.get("origin", {})

    return {
        "entity": sidecar_data.get("entity", ""),
        "workflow": sidecar_data.get("workflow", ""),
        "expense_date": expense.get("expense_date", ""),
        "vendor": expense.get("vendor", ""),
        "total_amount": expense.get("total_amount", ""),
        "currency": expense.get("currency", ""),
        "document_id": sidecar_data.get("id", ""),
        "archive_path": expense.get("source_path", ""),
        # Recommended columns
        "tax_amount": expense.get("tax_amount", ""),
        "invoice_number": expense.get("invoice_number", ""),
        "payment_method": expense.get("payment_method", ""),
        "category": expense.get("category", ""),
        "cost_center": expense.get("cost_center", ""),
        "memo": expense.get("memo", ""),
        "source": sidecar_data.get("source", ""),
        "origin_id": origin.get("message_id", ""),
        "created_at": sidecar_data.get("created_at", ""),
    }


def sidecar_to_xero_row(sidecar_data: dict) -> dict:
    """Convert a sidecar with expense data to a Xero bills CSV row.

    Args:
        sidecar_data: Parsed sidecar JSON

    Returns:
        Dictionary with Xero bills CSV column values

    Traceability per SOT:
        - Reference MUST include document_id
        - Description MUST include archive_path
    """
    expense = sidecar_data.get("accounting", {}).get("expense", {})
    document_id = sidecar_data.get("id", "")
    archive_path = expense.get("source_path", "")

    return {
        "ContactName": expense.get("vendor", ""),
        "InvoiceNumber": expense.get("invoice_number", ""),
        "InvoiceDate": expense.get("expense_date", ""),
        "DueDate": "",  # May be empty if unknown
        "Description": f"Archived: {archive_path}",
        "Quantity": "1",
        "UnitAmount": expense.get("total_amount", ""),
        "AccountCode": "",  # May be empty until configured per entity
        "TaxType": "",  # May be empty until configured per entity
        "Reference": f"archive:{document_id}",
    }


def export_expenses_csv(
    archive_path: Path | str,
    output_path: Path | str,
    entity: str | None = None,
) -> int:
    """Export expenses from archive sidecars to CSV.

    Args:
        archive_path: Root path of the archive
        output_path: Path for output CSV file
        entity: Optional entity filter (e.g., "tsm")

    Returns:
        Number of expenses exported
    """
    archive_path = Path(archive_path)
    output_path = Path(output_path)

    rows = []
    for sidecar_path, sidecar_data in find_sidecars_with_expenses(archive_path, entity):
        row = sidecar_to_expense_row(sidecar_data, archive_path)
        rows.append(row)

    # Sort by expense_date for stable output
    rows.sort(key=lambda r: (r.get("expense_date", ""), r.get("document_id", "")))

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EXPENSES_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    logger.info(f"Exported {len(rows)} expenses to {output_path}")
    return len(rows)


def export_xero_bills_csv(
    archive_path: Path | str,
    output_path: Path | str,
    entity: str | None = None,
) -> int:
    """Export expenses from archive sidecars to Xero-compatible bills CSV.

    Args:
        archive_path: Root path of the archive
        output_path: Path for output CSV file
        entity: Optional entity filter (e.g., "tsm")

    Returns:
        Number of bills exported
    """
    archive_path = Path(archive_path)
    output_path = Path(output_path)

    rows = []
    for sidecar_path, sidecar_data in find_sidecars_with_expenses(archive_path, entity):
        row = sidecar_to_xero_row(sidecar_data)
        rows.append(row)

    # Sort by InvoiceDate for stable output
    rows.sort(key=lambda r: (r.get("InvoiceDate", ""), r.get("Reference", "")))

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=XERO_BILLS_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    logger.info(f"Exported {len(rows)} Xero bills to {output_path}")
    return len(rows)
