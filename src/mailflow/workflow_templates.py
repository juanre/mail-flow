# ABOUTME: Pre-configured workflow templates for common email processing use cases.
# ABOUTME: Provides practical defaults for receipts, bank statements, tax documents, contracts, and action items.

from typing import Any

WORKFLOW_TEMPLATES = {
    "receipts": {
        "summary": "Expense receipts and invoices",
        "doctype": "expense",
        "constraints": {
            "requires_evidence": ["invoice", "receipt"],
            "evidence_sources": ["attachment_pdf", "body_pdf"],
        },
    },
    "bank_statements": {
        "summary": "Bank statements and financial documents",
        "doctype": "statement",
        "constraints": {
            "requires_evidence": ["statement"],
            "evidence_sources": ["attachment_pdf", "body_pdf"],
        },
    },
    "tax_documents": {
        "summary": "Tax-related documents",
        "doctype": "tax-doc",
        "constraints": {
            "requires_evidence": ["tax-doc"],
            "evidence_sources": ["attachment_pdf", "body_pdf"],
        },
    },
    "contracts": {
        "summary": "Contracts and legal documents",
        "doctype": "contract",
        "constraints": {
            "requires_evidence": ["contract"],
            "evidence_sources": ["attachment_pdf", "body_pdf"],
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
