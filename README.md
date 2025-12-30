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

## Quick Setup

```bash
# 1. Install dependencies
make install

# 2. Configure environment (edit .env with your API keys)
cp .env.example .env
# Edit .env - add ANTHROPIC_API_KEY and/or OPENAI_API_KEY

# 3. Setup database (PostgreSQL with pgvector)
make setup-db

# 4. Verify configuration
make check-env

# 5. Initialize mailflow workflows
uv run mailflow init

# 6. Test with a dry-run
make train-dry DIR=~/Mail/sample-folder MAX=10
```

## Makefile Commands

The Makefile provides convenient targets for common operations:

```bash
make help          # Show all available commands

# Setup
make install       # Install dependencies (uv sync + playwright)
make setup-db      # Create PostgreSQL database and schema
make check-env     # Verify environment variables are configured

# Training (with persistent learning)
make train-dry DIR=~/Mail/folder           # Dry-run (no workflow execution)
make train DIR=~/Mail/folder               # Train and execute workflows
make train-dry DIR=~/Mail/folder MAX=100   # Limit to 100 emails
make train-gmail QUERY='label:INBOX'       # Train from Gmail

# Monitoring
make metrics       # Show classifier metrics
make status        # Show learning stats (local + database)
make db-stats      # Show database table sizes

# Development
make test          # Run tests
make lint          # Run linter
```

## Environment Variables

The `.env` file controls all configuration. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | **Yes** | PostgreSQL connection string |
| `ARCHIVIST_DB_SCHEMA` | **Yes** | Schema name (e.g., `archivist_mailflow`) |
| `ANTHROPIC_API_KEY` | For LLM | Anthropic API key (Claude models) |
| `OPENAI_API_KEY` | For LLM | OpenAI API key (embeddings + GPT) |
| `ARCHIVIST_PERSIST_EMBED` | Optional | Set to `1` to store embeddings |
| `ARCHIVIST_LLM_BUDGET_USD` | Optional | Daily spending cap for LLM |

See `.env.example` for full documentation of all variables.

## Learning Architecture

mailflow uses **two learning systems** that work together:

1. **Local JSON** (`~/.local/share/mailflow/criteria_instances.json`)
   - Stores training examples for similarity matching
   - Fast, works offline
   - Used by the local similarity advisor

2. **PostgreSQL Database** (llm-archivist)
   - Stores decisions, feedback, and embeddings
   - Powers vector similarity search
   - Enables LLM-assisted classification
   - **Required for persistent learning** - without it, learning is lost when process exits

### How Learning Works

When you classify an email:
1. **Decision recorded**: The classification is stored in the database
2. **Feedback recorded**: Your confirmation trains the model
3. **Embedding stored**: Vector representation for similarity search
4. **Local example added**: For fast local matching

The system improves over time as you classify more emails.

## Installation (Detailed)

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

mailflow integrates with the llm-archivist library for intelligent classification.

**Setup**: Use `make setup-db` to create the database, or see `.env.example` for manual configuration.

**Training workflow**:
```bash
# 1. Verify environment
make check-env

# 2. Dry-run to train without executing workflows
make train-dry DIR=~/Mail/folder MAX=100

# 3. Check learning progress
make metrics

# 4. Run for real when confident
make train DIR=~/Mail/folder
```

**Notes**:
- Migrations are applied automatically on first run
- `DATABASE_URL` must be set for persistent learning
- The UI records your selection as training and sends feedback to llm-archivist

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
