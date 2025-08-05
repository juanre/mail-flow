"""Pre-configured workflow templates for common use cases"""

from typing import Dict, Any

# Workflow templates organized by entity and purpose
WORKFLOW_TEMPLATES = {
    # GreaterSkies workflows
    "gsk_expense": {
        "name": "gsk-expense",
        "description": "Save GreaterSkies expenses",
        "action_type": "save_pdf",
        "action_params": {
            "directory": "~/Documents/pmail/gsk/expense",
            "filename_template": "{date}_{from}_{subject}",
        },
    },
    "gsk_tax": {
        "name": "gsk-tax-doc",
        "description": "Save GreaterSkies tax documents",
        "action_type": "save_pdf",
        "action_params": {
            "directory": "~/Documents/pmail/gsk/tax-doc",
            "filename_template": "{date}_TAX_{from}_{subject}",
        },
    },
    "gsk_doc": {
        "name": "gsk-doc",
        "description": "Save GreaterSkies general documents",
        "action_type": "save_pdf",
        "action_params": {
            "directory": "~/Documents/pmail/gsk/doc",
            "filename_template": "{date}_{from}_{subject}",
        },
    },
    # TheStarMaps workflows
    "tsm_expense": {
        "name": "tsm-expense",
        "description": "Save TheStarMaps expenses",
        "action_type": "save_pdf",
        "action_params": {
            "directory": "~/Documents/pmail/tsm/expense",
            "filename_template": "{date}_{from}_{subject}",
        },
    },
    "tsm_tax": {
        "name": "tsm-tax-doc",
        "description": "Save TheStarMaps tax documents",
        "action_type": "save_pdf",
        "action_params": {
            "directory": "~/Documents/pmail/tsm/tax-doc",
            "filename_template": "{date}_TAX_{from}_{subject}",
        },
    },
    "tsm_doc": {
        "name": "tsm-doc",
        "description": "Save TheStarMaps general documents",
        "action_type": "save_pdf",
        "action_params": {
            "directory": "~/Documents/pmail/tsm/doc",
            "filename_template": "{date}_{from}_{subject}",
        },
    },
    # Personal (Juan Reyero) workflows
    "jro_expense": {
        "name": "jro-expense",
        "description": "Save Juan Reyero expenses",
        "action_type": "save_pdf",
        "action_params": {
            "directory": "~/Documents/pmail/jro/expense",
            "filename_template": "{date}_{from}_{subject}",
        },
    },
    "jro_tax": {
        "name": "jro-tax-doc",
        "description": "Save Juan Reyero tax documents",
        "action_type": "save_pdf",
        "action_params": {
            "directory": "~/Documents/pmail/jro/tax-doc",
            "filename_template": "{date}_TAX_{from}_{subject}",
        },
    },
    "jro_doc": {
        "name": "jro-doc",
        "description": "Save Juan Reyero general documents",
        "action_type": "save_pdf",
        "action_params": {
            "directory": "~/Documents/pmail/jro/doc",
            "filename_template": "{date}_{from}_{subject}",
        },
    },
    # Generic workflows
    "newsletter_archive": {
        "name": "archive-newsletter",
        "description": "Archive newsletter as PDF",
        "action_type": "save_email_as_pdf",
        "action_params": {
            "directory": "~/Documents/pmail/newsletters",
            "filename_template": "{date}_{from}_newsletter",
        },
    },
    "save_invoice_only": {
        "name": "save-invoice-pdf",
        "description": "Save only PDF invoice attachments",
        "action_type": "save_attachment",
        "action_params": {"directory": "~/Documents/pmail/invoices", "pattern": "*.pdf"},
    },
}


def get_workflow_suggestions(email_data: Dict[str, Any]) -> list:
    """Suggest workflow templates based on email characteristics"""
    suggestions = []
    from_domain = email_data.get("features", {}).get("from_domain", "")
    subject = email_data.get("subject", "").lower()
    body = email_data.get("body", "").lower()

    # Combine subject and body for keyword searching
    content = f"{subject} {body}".lower()

    # Entity detection
    entity = None
    if any(word in content for word in ["greaterskies", "greater skies", "gsk"]):
        entity = "gsk"
    elif any(word in content for word in ["thestarmaps", "star maps", "tsm", "starmaps"]):
        entity = "tsm"
    elif any(word in from_domain for word in ["juanreyero", "jreyero"]):
        entity = "jro"

    # Document type detection
    doc_type = None

    # Tax document keywords
    tax_keywords = ["1099", "w2", "w-2", "tax", "irs", "form", "ein", "schedule"]
    if any(keyword in content for keyword in tax_keywords):
        doc_type = "tax"

    # Expense/receipt keywords
    expense_keywords = [
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
    if doc_type != "tax" and any(keyword in content for keyword in expense_keywords):
        doc_type = "expense"

    # Build suggestions based on detection
    if entity and doc_type == "tax":
        suggestions.append(f"{entity}_tax")
    elif entity and doc_type == "expense":
        suggestions.append(f"{entity}_expense")
    elif entity:
        suggestions.append(f"{entity}_doc")

    # Generic suggestions based on content
    if doc_type == "expense" and not entity:
        # Suggest all expense workflows
        suggestions.extend(["gsk_expense", "tsm_expense", "jro_expense"])

    # Newsletter detection
    newsletter_keywords = ["newsletter", "digest", "weekly", "monthly", "update", "news"]
    if any(keyword in subject for keyword in newsletter_keywords):
        suggestions.append("newsletter_archive")

    # Invoice with PDF attachment
    has_pdf = any(
        att.get("filename", "").lower().endswith(".pdf")
        for att in email_data.get("attachments", [])
    )
    if has_pdf and "invoice" in content:
        suggestions.append("save_invoice_only")

    return suggestions
