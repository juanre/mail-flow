"""Pre-configured workflow templates for common use cases"""

from typing import Dict, Any

# Example workflow configurations that users can create

WORKFLOW_TEMPLATES = {
    "personal_receipts": {
        "name": "receipts-personal",
        "description": "Save receipts I paid personally",
        "action_type": "save_pdf",
        "action_params": {
            "directory": "~/receipts/personal",
            "filename_template": "{date}_{from}_{subject}",
        },
    },
    "business_receipts": {
        "name": "receipts-business",
        "description": "Save receipts for business expenses",
        "action_type": "save_pdf",
        "action_params": {
            "directory": "~/receipts/business",
            "filename_template": "{date}_BIZ_{from}_{subject}",
        },
    },
    "greaterskies_receipts": {
        "name": "receipts-greaterskies",
        "description": "Save receipts paid by GreaterSkies",
        "action_type": "save_pdf",
        "action_params": {
            "directory": "~/receipts/greaterskies",
            "filename_template": "{date}_GS_{from}_{subject}",
        },
    },
    "starmaps_receipts": {
        "name": "receipts-starmaps",
        "description": "Save receipts paid by TheStarMaps",
        "action_type": "save_pdf",
        "action_params": {
            "directory": "~/receipts/starmaps",
            "filename_template": "{date}_SM_{from}_{subject}",
        },
    },
    "invoices_only": {
        "name": "save-invoices",
        "description": "Save only PDF invoice attachments",
        "action_type": "save_attachment",
        "action_params": {"directory": "~/invoices", "pattern": "*.pdf"},
    },
    "archive_newsletters": {
        "name": "archive-newsletters",
        "description": "Convert newsletters to PDF and archive",
        "action_type": "save_email_as_pdf",
        "action_params": {
            "directory": "~/archives/newsletters",
            "filename_template": "{date}_{from}_newsletter.pdf",
        },
    },
}


def get_workflow_suggestions(email_data: Dict[str, Any]) -> list:
    """Suggest workflow templates based on email characteristics"""
    suggestions = []
    from_domain = email_data.get("features", {}).get("from_domain", "")
    subject = email_data.get("subject", "").lower()
    has_pdf = any(
        att.get("filename", "").lower().endswith(".pdf")
        for att in email_data.get("attachments", [])
    )

    # Receipt-related keywords
    receipt_keywords = [
        "receipt",
        "invoice",
        "order",
        "payment",
        "billing",
        "subscription",
    ]
    is_receipt = any(keyword in subject for keyword in receipt_keywords)

    # Business domains
    business_domains = [
        "aws.amazon.com",
        "google.com",
        "github.com",
        "cloudflare.com",
        "digitalocean.com",
        "stripe.com",
        "shopify.com",
    ]
    is_business = any(domain in from_domain for domain in business_domains)

    # Suggest based on characteristics
    if is_receipt:
        if is_business:
            suggestions.append("business_receipts")
        else:
            suggestions.append("personal_receipts")

        if has_pdf:
            suggestions.append("invoices_only")

    # Newsletter detection
    newsletter_keywords = ["newsletter", "digest", "weekly", "monthly", "update"]
    if any(keyword in subject for keyword in newsletter_keywords):
        suggestions.append("archive_newsletters")

    return suggestions
