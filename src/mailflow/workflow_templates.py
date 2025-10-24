# ABOUTME: Pre-configured workflow templates for common email processing use cases.
# ABOUTME: Provides practical defaults for receipts, bank statements, tax documents, contracts, and action items.

from typing import Any

WORKFLOW_TEMPLATES = {
    "receipts": {
        "name": "receipts",
        "description": "Save receipts and invoices (PDF attachments or convert email)",
        "action_type": "save_pdf",
        "action_params": {
            "pattern": "*.pdf",
        },
    },
    "bank_statements": {
        "name": "bank_statements",
        "description": "Save bank statements and financial documents",
        "action_type": "save_attachment",
        "action_params": {
            "pattern": "*.pdf",
        },
    },
    "tax_documents": {
        "name": "tax_documents",
        "description": "Save tax-related documents",
        "action_type": "save_pdf",
        "action_params": {
            "pattern": "*.pdf",
        },
    },
    "contracts": {
        "name": "contracts",
        "description": "Save contracts and legal documents",
        "action_type": "save_attachment",
        "action_params": {
            "pattern": "*.pdf",
        },
    },
    "action_required": {
        "name": "action_required",
        "description": "Create todo for emails requiring action",
        "action_type": "create_todo",
        "action_params": {
            "todo_file": "~/todos.txt",
        },
    },
}


def get_workflow_suggestions(email_data: dict[str, Any]) -> list:
    """Suggest workflow templates based on email characteristics"""
    suggestions = []
    subject = email_data.get("subject", "").lower()
    body = email_data.get("body", "").lower()

    # Combine subject and body for keyword searching
    content = f"{subject} {body}".lower()

    # Newsletter detection
    newsletter_keywords = ["newsletter", "digest", "weekly", "monthly", "update", "news"]
    if any(keyword in subject for keyword in newsletter_keywords):
        suggestions.append("newsletter_archive")

    # Invoice/receipt detection
    receipt_keywords = [
        "invoice",
        "receipt",
        "bill",
        "payment",
        "charge",
        "subscription",
        "purchase",
        "order",
        "statement",
        "expense",
        "cost",
        "fee",
    ]
    if any(keyword in content for keyword in receipt_keywords):
        suggestions.append("receipts_general")

    # Invoice with PDF attachment
    has_pdf = any(
        att.get("filename", "").lower().endswith(".pdf")
        for att in email_data.get("attachments", [])
    )
    if has_pdf and any(keyword in content for keyword in ["invoice", "receipt"]):
        suggestions.append("attachments_only")

    return suggestions
