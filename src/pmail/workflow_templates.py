"""Pre-configured workflow templates for common use cases"""

from typing import Any

# Generic workflow templates
WORKFLOW_TEMPLATES = {
    "receipts_general": {
        "name": "save-receipts",
        "description": "Save receipts and invoices as PDFs",
        "action_type": "save_pdf",
        "action_params": {
            "directory": "~/Documents/pmail/receipts",
            "filename_template": "{date}-{from}-{subject}",
        },
    },
    "newsletter_archive": {
        "name": "archive-newsletter",
        "description": "Archive newsletter as PDF",
        "action_type": "save_email_as_pdf",
        "action_params": {
            "directory": "~/Documents/pmail/newsletters",
            "filename_template": "{date}-{from}-newsletter",
        },
    },
    "attachments_only": {
        "name": "save-attachments",
        "description": "Save PDF attachments only",
        "action_type": "save_attachment",
        "action_params": {"directory": "~/Documents/pmail/attachments", "pattern": "*.pdf"},
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
