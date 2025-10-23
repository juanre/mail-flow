# mailflow Workflow Examples

## Receipts and Invoices

The `save_pdf` action intelligently handles both PDF attachments and HTML receipts:

```json
{
  "amazon-receipts": {
    "name": "amazon-receipts",
    "description": "Save Amazon orders",
    "action_type": "save_pdf",
    "action_params": {
      "directory": "~/receipts/personal/amazon",
      "filename_template": "{date}_order_{subject}"
    }
  },
  "utility-bills": {
    "name": "utility-bills",
    "description": "Save utility bills",
    "action_type": "save_pdf",
    "action_params": {
      "directory": "~/bills/utilities",
      "filename_template": "{date}_{from}_bill"
    }
  },
  "business-expenses": {
    "name": "business-expenses",
    "description": "Business expenses",
    "action_type": "save_pdf",
    "action_params": {
      "directory": "~/receipts/business",
      "filename_template": "{date}_biz_{from}_{subject}"
    }
  }
}
```

## Organization

```json
{
  "archive-newsletters": {
    "name": "archive-newsletters",
    "description": "Archive newsletters",
    "action_type": "create_todo",
    "action_params": {"todo_file": "~/newsletters.txt"}
  }
}
```

## Workflow Creation Flow

### Interactive
```bash
# Process email, select "new"
Selection: new
Workflow name: save-receipts
Description: Personal receipts
Action type: save_pdf
Directory: ~/receipts/personal
Filename template: {date}_{from}_{subject}
```

### Direct Edit
Edit `~/.config/mailflow/workflows.json` directly with your favorite editor.

## Multi-Entity Organization

For managing multiple entities (business, personal, etc.):

```bash
# Use the interactive setup
uv run mailflow setup-workflows

# Example: Enter entities like "biz" and "personal"
# Example: Enter doc types like "expense" and "tax-doc"
```

Example directory structure:
```
~/Documents/mailflow/
  ├── business/
  │   ├── expense/
  │   └── tax-doc/
  └── personal/
      ├── expense/
      └── tax-doc/
```

Workflows created: business-expense, business-tax-doc, personal-expense, personal-tax-doc
