# mailflow - Smart Email Processing for Mutt

Email processing tool for mutt that learns from your classification choices and suggests workflows using similarity matching and optional LLM assistance. Storage uses a single v2 layout (docs/ + nested streams/), and a global index powers fast search across entities.

## Features

- **Similarity-Based Learning**: Learns from your email classification decisions
- **Optional LLM Enhancement**: AI-powered classification for ambiguous cases
- **Hybrid Classification**: Fast similarity matching with LLM fallback
- **Deduplication**: Tracks processed emails to prevent reprocessing
- **Batch Processing**: Process thousands of emails efficiently
- **Flexible Workflows**: Save PDFs, create todos, flag emails, etc.
- **Global Search**: Build a global index once, then search across all entities
- **Gmail API**: Process emails directly from Gmail (optional)

## Installation

```bash
# Clone and install
git clone <repo-url>
cd mail-flow

# Requires Python 3.12+

# Install with uv
uv sync

# Install Playwright for PDF generation
playwright install chromium

# Initialize configuration
uv run mailflow init
```

### One-time setup on a new machine

On a fresh machine, the recommended sequence is:

1. Install dependencies as above (`uv sync`, Playwright).
2. Create a `.env` file in the project root (next to `pyproject.toml`) with:
   - Archivist DB config: `ARCHIVIST_USE_DB`, `DATABASE_URL`, `ARCHIVIST_DB_SCHEMA`, `ARCHIVIST_DB_NAME`.
   - LLM keys: at least `OPENAI_API_KEY` (and optionally `ANTHROPIC_API_KEY`).
3. Initialize the archivist database (see “Classifier Integration” below).
4. Run `uv run mailflow init` to create mailflow config and workflows.
5. Do a small dry-run batch on a representative Maildir to confirm everything works.

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

# Fetch + process from Gmail (OAuth)
uv run mailflow fetch gmail --query "label:INBOX newer_than:1d"

# Process local emails from files or Maildir folders
uv run mailflow fetch files ~/mail/archive --dry-run

# Force reprocess already-processed emails
uv run mailflow --force < email.eml

# Build global indexes (from your archive base)
uv run mailflow index --base ~/Archive

# Search globally (with optional filters)
uv run mailflow gsearch "invoice" --entity acme --limit 10

# Show indexed information for a file
uv run mailflow data docs/2025/2025-11-05-invoice-1234.pdf

# List workflows
uv run mailflow workflows

# Show statistics
uv run mailflow stats
```

## Classifier Integration (llm-archivist)

mailflow integrates with the llm-archivist library. It is enabled by default and runs in dev mode (no DB/LLM) unless you configure it. For a full‑fledged setup (Postgres + pgvector + LLM), follow the steps below.

```bash
# 1) Database (Postgres) – one‑time setup (psql)
CREATE DATABASE archivist_mailflow;
CREATE USER archivist WITH PASSWORD 'changeme';
GRANT ALL PRIVILEGES ON DATABASE archivist_mailflow TO archivist;
\c archivist_mailflow
CREATE SCHEMA IF NOT EXISTS archivist_mailflow;
-- pgvector: llm‑archivist migrations will attempt this automatically;
-- if your role cannot create extensions, have an admin pre‑install it.
CREATE EXTENSION IF NOT EXISTS vector;

# 2) Environment (.env in project root or shell exports)
# Example values – adjust user/password/host as needed
ARCHIVIST_USE_DB=1
DATABASE_URL='postgresql://archivist:changeme@localhost:5432/archivist_mailflow'
ARCHIVIST_DB_SCHEMA=archivist_mailflow
ARCHIVIST_DB_NAME=archivist_mailflow
OPENAI_API_KEY=...     # required for embeddings + LLM
# Optional safety controls
ARCHIVIST_PERSIST_EMBED=1        # store embeddings after decisions
ARCHIVIST_LLM_BUDGET_USD=5       # cap spending
ARCHIVIST_LLM_RETRIES=1          # retry LLM on transient failures

# 3) Bootstrap – create schema and apply migrations via llm‑archivist
uv run python -m llm_archivist.cli db-init --bootstrap

# 4) Dry‑run training from files/Maildir (no writes; trains both systems)
uv run mailflow fetch files ~/Mail/juan-gsk --dry-run

# 5) Apply for real after training
uv run mailflow fetch files ~/Mail/juan-gsk

# 6) Sanity check archivist metrics (optional)
uv run mailflow archivist-metrics
```

Notes
- Migrations are applied automatically on first run.
- In dev mode (no DB/LLM), the classifier still learns from your confirmations locally.
- The UI records your selection as training and also sends feedback to llm‑archivist so it improves over time.

## Optional Features

- Archive
  - `archive.base_path`: e.g., `~/Archive`
  - `archive.save_originals`: store attachment originals under `originals/`
  - `archive.originals_prefix_date`: prepend `yyyy-mm-dd-` to originals
  - `archive.convert_attachments`: convert text attachments to PDF; TSV→CSV
- Classifier
  - `classifier.enabled`: record suggestions in origin.classifier
  - `classifier.gate_enabled`: gate no-attachment emails (worth archiving?)
  - `classifier.gate_min_confidence`: e.g., 0.7

## Storage Layout (v2)

- {entity}/docs/{YYYY}/yyyy-mm-dd-normalised-file-name.pdf|csv
- {entity}/originals/{YYYY}/[optional yyyy-mm-dd-]Original Name.ext (when enabled)
- {entity}/streams/slack/{channel}/{YYYY}/yyyy-mm-dd-transcript.md
- indexes/{metadata.db, fts.db} (global)

Indexing and search:
- Build index: `uv run mailflow index --base ~/Archive`
- Search: `uv run mailflow gsearch "query" --entity acme --workflow invoices --limit 20`

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
uv run mailflow fetch gmail --query "label:INBOX newer_than:1d" --processed-label "mailflow/processed"
```

## Testing

```bash
uv run pytest -q
```

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
  process.py                   # Main pipeline (invoked by CLI)
  cli.py                       # CLI entrypoint (registers subcommands)
  commands/
    index_search.py            # index, gsearch, data (global indexes)
    gmail_batch_workflows.py   # gmail, batch, workflows + fetch aliases

Lint & tests:
```bash
uv run ruff check .
uv run pytest -q
```
```

## License

MIT
