# pmail Examples

## Setting Up Multiple Receipt Workflows

The key to organizing receipts is creating separate workflows for each payment source. The `save_pdf` function automatically handles both PDF attachments and emails without attachments (converts them to PDF).

### Creating Multiple Workflows

Create separate workflows for different payment sources:

```
--- Create New Workflow ---
Workflow name: receipts-personal
Description: Receipts I paid personally
Action type: save_pdf
Directory: ~/receipts/personal
Filename template (for emails without PDF): {date}_{from}_{subject}

--- Create New Workflow ---
Workflow name: receipts-greaterskies  
Description: Receipts paid by GreaterSkies
Action type: save_pdf
Directory: ~/receipts/greaterskies
Filename template (for emails without PDF): {date}_GS_{from}_{subject}

--- Create New Workflow ---
Workflow name: receipts-starmaps
Description: Receipts paid by TheStarMaps  
Action type: save_pdf
Directory: ~/receipts/starmaps
Filename template (for emails without PDF): {date}_SM_{from}_{subject}
```

### Using Workflow Templates

For quick setup, use the pre-configured templates:

```
Use a workflow template? yes

Available templates:
  - personal_receipts: Save receipts I paid personally
  - business_receipts: Save receipts for business expenses  
  - greaterskies_receipts: Save receipts paid by GreaterSkies
  - starmaps_receipts: Save receipts paid by TheStarMaps
  - invoices_only: Save only PDF invoice attachments
  - archive_newsletters: Convert newsletters to PDF and archive

Template name: personal_receipts
✓ Using template: Save receipts I paid personally
```

## How save_pdf Works

The `save_pdf` action is smart:

1. **If the email has PDF attachments**: Saves the PDF files directly with their original names
2. **If no PDF attachments**: Converts the email itself to PDF using your filename template

This handles both cases:
- Amazon sends invoices as PDF attachments → saves "Invoice_12345.pdf"
- Stripe sends HTML receipts → converts to "20240120_stripe.com_Payment_Receipt.pdf"

## Example Directory Structure

After setting up multiple workflows, your receipts might be organized like:

```
~/receipts/
├── personal/
│   ├── amazon/
│   │   ├── Order_123456.pdf
│   │   └── Order_789012.pdf
│   ├── apple/
│   │   └── Receipt_App_Store.pdf
│   └── subscriptions/
│       ├── 20240115_spotify.com_Monthly_Invoice.pdf
│       └── 20240120_netflix.com_Subscription.pdf
├── greaterskies/
│   ├── aws/
│   │   └── AWS_Invoice_January_2024.pdf
│   └── infrastructure/
│       └── Cloudflare_Invoice.pdf
└── starmaps/
    └── 20240110_SM_supplier_Invoice_4521.pdf
```

## Workflow Examples in ~/.pmail/workflows.json

```json
{
  "receipts-personal": {
    "name": "receipts-personal",
    "description": "Receipts I paid personally",
    "action_type": "save_pdf",
    "action_params": {
      "directory": "~/receipts/personal",
      "filename_template": "{date}_{from}_{subject}"
    }
  },
  "receipts-greaterskies": {
    "name": "receipts-greaterskies",
    "description": "Receipts paid by GreaterSkies",
    "action_type": "save_pdf",
    "action_params": {
      "directory": "~/receipts/greaterskies",
      "filename_template": "{date}_GS_{from}_{subject}"
    }
  },
  "receipts-starmaps": {
    "name": "receipts-starmaps",
    "description": "Receipts paid by TheStarMaps",
    "action_type": "save_pdf",
    "action_params": {
      "directory": "~/receipts/starmaps",
      "filename_template": "{date}_SM_{from}_{subject}"
    }
  }
}
```

## Tips

1. **Create separate workflows** for each payment source (personal, each company, etc.)
2. **Use consistent naming** like `receipts-xxx` to group related workflows
3. **Add prefixes to filenames** to identify the payer (e.g., `GS_` for GreaterSkies)
4. **The system learns** - after you select a workflow for an email, it will suggest it for similar emails

## Integration with mutt

In your `.muttrc`:
```
# Pipe email to pmail
macro index,pager ,p "<pipe-message>pmail<enter>" "Process with pmail"

# Quick shortcuts for specific workflows
macro index,pager ,pp "<pipe-message>pmail --workflow save-personal<enter>" "Save personal receipt"
macro index,pager ,pb "<pipe-message>pmail --workflow save-business<enter>" "Save business receipt"
macro index,pager ,pg "<pipe-message>pmail --workflow save-greaterskies<enter>" "Save GreaterSkies receipt"
```