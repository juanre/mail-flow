# pmail - Smart Email Processing for Mutt

pmail is an email processing tool designed to work with mutt. It learns from your email classification choices and suggests appropriate workflows for similar emails.

## Features

- **Learning System**: Learns from your email classification decisions
- **Similarity Matching**: Uses feature extraction and similarity scoring to suggest workflows
- **Flexible Workflows**: Define custom actions like saving attachments, flagging emails, etc.
- **Mutt Integration**: Designed to work seamlessly with mutt via pipe commands
- **Accretion**: Gets better at predictions over time as you use it

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd mail-flow

# Install with pip (in a virtual environment)
pip install -e .

# Install Playwright browsers for PDF generation (needed for email-to-PDF)
playwright install chromium

# Initialize pmail with default configuration
pmail init
```

## Quick Start

1. **Initialize pmail**:
```bash
pmail init
```
This creates:
- Configuration directory at `~/.pmail/`
- Default workflows for common use cases
- Directories for organizing PDFs

2. **Add to your .muttrc**:
```muttrc
# Process email with pmail (Ctrl-P)
macro index,pager \cp "<pipe-message>pmail<enter>" "Process with pmail"
```

3. **First Use**:
   - Press Ctrl-P on any email in mutt
   - pmail will show you available workflows
   - Select or create a new workflow
   - The system learns from your choice

4. **Subsequent Uses**:
   - pmail will suggest workflows based on similar emails
   - The most likely workflow is pre-selected
   - Just press Enter to accept, or choose a different one

## How It Works

### Learning Process

1. **Feature Extraction**: pmail extracts features from each email:
   - Sender domain
   - Subject keywords
   - Presence of attachments (PDFs, images, etc.)
   - Body content keywords

2. **Similarity Scoring**: When processing a new email, pmail:
   - Compares it to previous classified emails
   - Calculates similarity scores based on feature matches
   - Ranks workflows by confidence

3. **Accretion**: The system improves over time:
   - Every classification is saved as a training example
   - Older criteria are equally valuable (no time-based decay)
   - System gets better at recognizing patterns with more examples

### Workflows

Workflows define what happens to an email. Built-in types include:

- **save_attachment**: Save attachments to a directory
- **save_pdf**: Save PDF attachments OR convert email to PDF if no PDFs found
- **save_email_as_pdf**: Always convert the email itself to PDF
- **flag**: Add a flag to the email in mutt
- **copy_to_folder**: Copy email to another folder
- **create_todo**: Extract a todo item from the email

## Command Line Interface

```bash
# Initialize configuration
pmail init
pmail init --reset  # Reset existing configuration

# List workflows
pmail workflows
pmail workflows --limit 20

# Show statistics
pmail stats

# Search PDFs
pmail search "invoice"
pmail search --directory ~/receipts --type invoice
pmail search --limit 50

# Show version
pmail version

# Fetch from Gmail via API (optional; see Gmail section below)
pmail gmail --query "label:INBOX -label:pmail/processed newer_than:1d" --processed-label "pmail/processed" --max-results 20
```

## Configuration

Configuration is stored in `~/.pmail/`:

- `config.json`: Feature weights and UI settings
- `workflows.json`: Workflow definitions
- `criteria_instances.json`: Learning history

### Creating Your First Workflows

#### Option 1: Interactive Creation
When processing an email, select "new" to create a workflow:

```
Selection: new
Workflow name: save-receipts
Description: Save personal receipts
Use a workflow template? [no]: no
Action type: save_pdf
Directory: ~/receipts/personal
Filename template: {date}_{from}_{subject}
```

#### Option 2: Edit workflows.json
Create `~/.config/pmail/workflows.json`:

```json
{
  "save-personal-receipts": {
    "name": "save-personal-receipts",
    "description": "Save personal receipts/invoices",
    "action_type": "save_pdf",
    "action_params": {
      "directory": "~/receipts/personal",
      "filename_template": "{date}_{from}_{subject}"
    },
    "created_at": "2024-01-15T10:00:00"
  },
  "save-business-receipts": {
    "name": "save-business-receipts",
    "description": "Save business receipts/invoices",
    "action_type": "save_pdf",
    "action_params": {
      "directory": "~/receipts/business",
      "filename_template": "{date}_{from}_{subject}"
    },
    "created_at": "2024-01-15T10:00:00"
  }
}
```

### Feature Weights

Adjust how important each feature is for matching:

```json
{
  "feature_weights": {
    "from_domain": 0.3,
    "subject_similarity": 0.25,
    "has_pdf": 0.2,
    "body_keywords": 0.15,
    "to_address": 0.1
  }
}
```

## Workflow Examples

### Receipt/Invoice Workflows
The `save_pdf` action is intelligent:
- If the email has PDF attachments, it saves them
- If no PDFs found, it converts the email itself to PDF

```json
{
  "amazon-receipts": {
    "name": "amazon-receipts",
    "description": "Save Amazon receipts",
    "action_type": "save_pdf",
    "action_params": {
      "directory": "~/receipts/amazon",
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
  }
}
```

### Organization Workflows
```json
{
  "flag-urgent": {
    "name": "flag-urgent",
    "description": "Flag as urgent",
    "action_type": "flag",
    "action_params": {"flag": "urgent"}
  },
  "archive-newsletters": {
    "name": "archive-newsletters",
    "description": "Archive newsletters",
    "action_type": "copy_to_folder",
    "action_params": {"folder": "Newsletters"}
  }
}
```

### Example Learning Process

1. **First Invoice**: You receive an Amazon invoice with PDF
   - pmail shows default workflows
   - You create "save-personal-receipts" → ~/receipts/personal
   - pmail saves the PDF and learns this pattern

2. **Second Invoice**: Business expense from vendor
   - pmail suggests "save-personal-receipts" (60% confidence)
   - You create "save-business-receipts" → ~/receipts/business
   - pmail now knows two patterns

3. **Third Invoice**: Another Amazon order
   - pmail correctly suggests "save-personal-receipts" (85% confidence)
   - Just press Enter to accept
   - System gets more confident with each use

## Demo

Run the demo to see how pmail learns:

```bash
python docs/demo.py
```

The demo will:
1. Train on sample emails
2. Show prediction accuracy
3. Demonstrate the interactive UI

## Testing

Run tests with pytest:

```bash
uv run pytest -q
```

## Running pmail

### Using a local copy (mutt or stdin)
- Add the macro to `.muttrc` (see above) and press Ctrl-P in mutt to pipe the message into `pmail`.
- Or run `pmail` reading from stdin:
  ```bash
  cat message.eml | uv run pmail
  ```

### Using Gmail API (no local mailbox)
Optional integration that fetches emails from Gmail and processes them through the same pipeline.

Requirements:
- Install Gmail API deps:
  ```bash
  uv add google-api-python-client google-auth google-auth-oauthlib
  ```
- Create an OAuth 2.0 Client (Desktop) in Google Cloud Console and download the JSON.
- Save it to `~/.pmail/gmail_client_secret.json`.

First run will open a browser for consent and store tokens at `~/.pmail/gmail_token.json`.

Examples:
```bash
# Process recent inbox messages, label them after processing
uv run pmail gmail --query "label:INBOX newer_than:1d" --processed-label "pmail/processed"

# Only process messages with a custom queue label and remove from INBOX after processing
uv run pmail gmail --label "pmail/queue" --processed-label "pmail/processed" --remove-from-inbox

# Limit batch size
uv run pmail gmail --query "label:INBOX" --max-results 10
```

Notes:
- Keep using your local-copy flow; Gmail fetch is optional and does not change existing behavior.
- After processing, messages can be labeled (e.g., `pmail/processed`) and optionally removed from INBOX.
- You can set up a cron/launchd job to periodically run the command.

### Semantic search with llmemory (optional)
pmail can optionally index saved PDFs/emails into `llmemory` for hybrid (semantic + text) search at scale.

Requirements:
- PostgreSQL 14+ with the `pgvector` extension installed and enabled.
- Install the dependency:
  ```bash
  uv add llmemory
  ```

Enable in config (`~/.pmail/config.json`):
```json
{
  "llmemory": {
    "enabled": true,
    "connection_string": "postgresql://user:pass@localhost:5432/pmail",
    "owner_id": "default-owner",
    "embedding_provider": "openai",
    "openai_api_key": "sk-..."
  }
}
```

How it works:
- When a PDF is saved (attachment or converted email), pmail stores metadata in SQLite as usual and, if `llmemory.enabled` is true and text is available, also indexes the content in llmemory with useful metadata (workflow, document type/category, email headers).

Search with llmemory:
```bash
uv run pmail msearch "cloudflare invoice" --limit 10
```

Notes:
- This is completely optional and does not change the default SQLite FTS search. Use `pmail search` (SQLite) or `pmail msearch` (llmemory) based on needs.
- llmemory supports local embedding providers; set `embedding_provider` accordingly and omit `openai_api_key` if using local.

## Development

### Project Structure

```
pmail/
   src/pmail/
      config.py          # Configuration management
      email_extractor.py # Email parsing and feature extraction
      models.py          # Data models and persistence
      similarity.py      # Similarity scoring engine
      ui.py              # Interactive workflow selection
      process.py         # Main entry point
      workflow.py        # Workflow definitions and actions
   tests/                 # Test suite
      res/              # Sample emails for testing
   demo.py               # Interactive demo
```

### Adding New Workflow Types

1. Add the action function to `workflow.py`
2. Register it in the `Workflows` dictionary
3. Users can create workflows using your new action type

## License

[Your license here]

## Contributing

[Contributing guidelines]
