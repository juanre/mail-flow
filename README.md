# mailflow - Smart Email Processing for Mutt

Email processing tool for mutt that learns from your classification choices and suggests workflows using similarity matching and optional LLM assistance.

## Features

- **Similarity-Based Learning**: Learns from your email classification decisions
- **Optional LLM Enhancement**: AI-powered classification for ambiguous cases
- **Hybrid Classification**: Fast similarity matching with LLM fallback
- **Deduplication**: Tracks processed emails to prevent reprocessing
- **Batch Processing**: Process thousands of emails efficiently
- **Flexible Workflows**: Save PDFs, create todos, flag emails, etc.
- **Full-Text Search**: Find saved PDFs by content
- **Gmail API**: Process emails directly from Gmail (optional)

## Installation

```bash
# Clone and install
git clone <repo-url>
cd mail-flow

# Install with uv
uv sync

# Install Playwright for PDF generation
playwright install chromium

# Initialize configuration
uv run mailflow init
```

## Quick Start

```bash
# 1. Initialize mailflow (interactive setup)
uv run mailflow init

# This will ask you to define:
# - Your entities (e.g., jro, tsm, gsk)
# - Document types (e.g., expense, invoice, tax-doc)
# And create workflows for each combination

# 2. Add to .muttrc
macro index,pager \cp "<pipe-message>mailflow<enter>" "Process with mailflow"

# 3. Process emails
# Press Ctrl-P in mutt, mailflow learns from your choices
```

## Commands

```bash
# Process email from stdin
cat email.eml | uv run mailflow

# Enable LLM assistance (requires API key)
cat email.eml | uv run mailflow --llm

# Batch process directory
uv run mailflow batch ~/mail/archive --llm --dry-run

# Force reprocess already-processed emails
uv run mailflow --force < email.eml

# Search saved PDFs
uv run mailflow search "invoice"
uv run mailflow search --directory ~/receipts --type invoice

# List workflows
uv run mailflow workflows

# Show statistics
uv run mailflow stats
```

## LLM Integration (Optional)

Enable AI-powered classification for better accuracy:

```bash
# 1. Set API key
export ANTHROPIC_API_KEY=sk-ant-...
# or OPENAI_API_KEY or GOOGLE_GEMINI_API_KEY

# 2. Enable in config (~/.config/mailflow/config.json)
{
  "llm": {
    "enabled": true,
    "model_alias": "balanced"  # fast, balanced, or deep
  }
}

# 3. Process emails with LLM
cat email.eml | uv run mailflow --llm
```

**How it works:**
- High confidence (≥85%): Uses similarity only (fast, free)
- Medium confidence (50-85%): Shows both similarity and AI suggestions
- Low confidence (<50%): Uses AI as primary suggestion

**Cost:** ~$0.003 per email with LLM, but hybrid approach only uses LLM for ~20% of emails (~$6 for 10,000 emails).

## Configuration

mailflow follows the XDG Base Directory specification:

**Config** (`~/.config/mailflow/` or `$XDG_CONFIG_HOME/mailflow/`):
- `config.json`: Feature weights, UI settings, LLM configuration
- `workflows.json`: Workflow definitions
- `processed_emails.db`: Deduplication tracking
- `gmail_client_secret.json`: OAuth credentials (if using Gmail API)

**Data** (`~/.local/share/mailflow/` or `$XDG_DATA_HOME/mailflow/`):
- `criteria_instances.json`: Learning history (training data)

**State/Logs** (`~/.local/state/mailflow/` or `$XDG_STATE_HOME/mailflow/`):
- `logs/`: Application logs
- `history/`: Command history

## Workflows

Built-in workflow types:
- **save_pdf**: Save PDF attachments OR convert email to PDF
- **save_attachment**: Save attachments to directory
- **save_email_as_pdf**: Always convert email to PDF
- **create_todo**: Extract todo from email

## Gmail API (Optional)

Process emails directly from Gmail:

```bash
# Setup: Place OAuth 2.0 client JSON at ~/.config/mailflow/gmail_client_secret.json

# Process inbox
uv run mailflow gmail --query "label:INBOX newer_than:1d" --processed-label "mailflow/processed"
```

## Testing

```bash
uv run pytest -q
```

## Running mailflow

### Using a local copy (mutt or stdin)
- Add the macro to `.muttrc` (see above) and press Ctrl-P in mutt to pipe the message into `mailflow`.
- Or run `mailflow` reading from stdin:
  ```bash
  cat message.eml | uv run mailflow
  ```

### Using Gmail API (no local mailbox)
Optional integration that fetches emails from Gmail and processes them through the same pipeline.

Requirements:
- Install Gmail API deps:
  ```bash
  uv add google-api-python-client google-auth google-auth-oauthlib
  ```
- Create an OAuth 2.0 Client (Desktop) in Google Cloud Console and download the JSON.
- Save it to `~/.config/mailflow/gmail_client_secret.json`.

First run will open a browser for consent and store tokens at `~/.config/mailflow/gmail_token.json`.

Examples:
```bash
# Process recent inbox messages, label them after processing
uv run mailflow gmail --query "label:INBOX newer_than:1d" --processed-label "mailflow/processed"

# Only process messages with a custom queue label and remove from INBOX after processing
uv run mailflow gmail --label "mailflow/queue" --processed-label "mailflow/processed" --remove-from-inbox

# Limit batch size
uv run mailflow gmail --query "label:INBOX" --max-results 10
```

Notes:
- Keep using your local-copy flow; Gmail fetch is optional and does not change existing behavior.
- After processing, messages can be labeled (e.g., `mailflow/processed`) and optionally removed from INBOX.
- You can set up a cron/launchd job to periodically run the command.

### Semantic search with llmemory (optional)
mailflow can optionally index saved PDFs/emails into `llmemory` for hybrid (semantic + text) search at scale.

Requirements:
- PostgreSQL 14+ with the `pgvector` extension installed and enabled.
- Install the dependency:
  ```bash
  uv add llmemory
  ```

Enable in config (`~/.config/mailflow/config.json`):
```json
{
  "llmemory": {
    "enabled": true,
    "connection_string": "postgresql://user:pass@localhost:5432/mailflow",
    "owner_id": "default-owner",
    "embedding_provider": "openai",
    "openai_api_key": "sk-..."
  }
}
```

How it works:
- When a PDF is saved (attachment or converted email), mailflow stores metadata in SQLite as usual and, if `llmemory.enabled` is true and text is available, also indexes the content in llmemory with useful metadata (workflow, document type/category, email headers).
- llmemory supports local embedding providers; set `embedding_provider` accordingly and omit `openai_api_key` if using local.

Search with llmemory:
```bash
uv run mailflow search "cloudflare invoice" --limit 10
uv run mailflow msearch "cloudflare invoice" --limit 10
```

Notes:
- This is completely optional and does not change the default SQLite FTS search. Use `mailflow search` (SQLite) or `mailflow msearch` (llmemory) based on needs.

### MCP server (optional)
Expose read-only tools over the Model Context Protocol so an MCP-enabled LLM (e.g., Claude Desktop) can query your archive.

Run the STDIO server:
```bash
uv run mailflow-mcp
```

Tools exposed:
- `search_pdfs`: text search across your archive (uses SQLite FTS under the hood)
- `get_pdf_metadata`: fetch full metadata for a PDF by path or filename
- `get_pdf_text_preview`: short text preview (PDF extracted text or email body)

Notes:
- The server waits for MCP messages on STDIO. Ctrl-C to stop.
- To test locally, use the stdio client from your `mailflow-mcp` repo or an MCP client.
## Development

Project structure:
```
src/mailflow/
  config.py                     # Configuration
  email_extractor.py           # Email parsing
  similarity.py                # Similarity matching
  llm_classifier.py            # LLM classification
  hybrid_classifier.py         # Hybrid routing
  processed_emails_tracker.py  # Deduplication
  workflow.py                  # Workflow execution
  ui.py                        # Interactive selection
  process.py                   # Main pipeline
  cli.py                       # CLI commands
```

## License

MIT
