# Status and Next Steps (2025-11-26)

## Current Status

### Architecture & Storage
- **Repository layout (v2) is adopted**: `{entity}/docs/{YYYY}/yyyy-mm-dd-name.pdf|csv`, `streams/<channel>/<yyyy>/<yyyy-mm-dd-transcript.md>`, and global indexes stored outside per-entity data.
- **Archive integration**: Workflows use `archive-protocol` to write documents, convert emails to PDF, and optionally convert attachments (text→PDF, TSV→CSV). Originals can be saved with optional date prefixes.
- **Global indexing/search**: `mailflow index` builds metadata/FTS SQLite databases; `mailflow gsearch` queries with filters (`--entity --workflow --source --category --limit`). Indexer docs live in `docs/indexer/`.

### Classification & Learning

**Design Decision (2025-11-26)**: For the current 4 workflows (gsk-invoice, gsk-receipt, tsm-invoice, tsm-receipt), the full llm-archivist stack (PostgreSQL + pgvector + OpenAI embeddings) is overkill. We chose to fix and use the simpler similarity-based classifier first:

- **Primary classifier**: Similarity engine using Jaccard similarity on email features (sender domain, subject keywords, body keywords, attachment info).
- **Feature extraction fix**: Added stopwords filtering to `email_extractor.py`. Previously stored common words ("a", "the", "and") with no discriminative value, causing bloated training data (270KB for ~100 entries).
- **Clean slate**: Removed stale `criteria_instances.json` that referenced non-existent workflows (save-invoices, save-errors, etc.). Training data now builds fresh from actual workflow selections.
- **llm-archivist integration**: Code exists and is tested, but NOT enabled by default. Available as upgrade path when workflow count or complexity justifies the infrastructure.

**Data storage**:
- Config: `~/.config/mailflow/` (config.json, workflows.json)
- Training data: `~/.local/share/mailflow/criteria_instances.json` (XDG spec)
- State/logs: `~/.local/state/mailflow/`

### Interactive TUI (2025-11-26)
New Rich-based TUI for email processing:
- **Email display**: Shows sender, subject, date, attachment indicators (PDF gets emoji), body preview with HTML→text conversion
- **Thread detection**: Groups related emails, shows position in thread, hints when PDF exists in another thread email
- **Workflow selection**: Numbered choices, confidence scores, suggested default
- **Actions**: `[s]` skip (records negative training), `[e]` expand full content, `[n]` next without action, `[?]` help
- **Ranking filter**: Only suggests workflows that actually exist (prevents stale training data from suggesting deleted workflows)

### CLI & Workflows
- **Workflow creation**: `uv run mailflow init` and `setup-workflows` build workflows; UI supports creating on-the-fly with templates.
- **Current workflows**: gsk-invoice, gsk-receipt, tsm-invoice, tsm-receipt
- **Fetch commands**: `uv run mailflow fetch gmail …` (Gmail API) and `uv run mailflow fetch files …` (directories or Maildir).
- **Dry run**: `--dry-run` on file/gmail fetch avoids writes while training classifiers.

### Repo & Dependencies
- **Python version**: Requires Python 3.12+.
- **Local deps**: `archive-protocol`, `file-classifier-core`, `llmring`, `pgdbm`, `html2text`, `rich`. Optional: `llm-archivist`.
- **Tests**: `uv run pytest` (236 tests) pass.

## Design Decisions Log

### 2025-11-26: Similarity Engine vs llm-archivist

**Context**: The similarity classifier was storing garbage features (stopwords) and the training data referenced workflows that no longer exist.

**Options considered**:
1. Enable llm-archivist (PostgreSQL + pgvector + OpenAI embeddings)
2. Fix the similarity engine feature extraction
3. Simple rule-based classification

**Decision**: Fix the similarity engine first.

**Rationale**:
- 4 workflows is not enough to justify PostgreSQL + pgvector setup
- The similarity engine algorithm (Jaccard) is fine; the bug was in feature extraction
- llm-archivist remains available as an upgrade path
- Start with a clean slate and let the classifier learn from actual usage

**Changes made**:
- Added STOPWORDS frozenset (~150 common words) to `email_extractor.py`
- Filter tokens: remove stopwords, keep only tokens >= 2 chars
- Removed stale training data (backed up to `criteria_instances.json.bak.20251126`)

### 2025-11-26: Interactive TUI Implementation

**Context**: The old UI was basic and lacked context for decision-making.

**Decision**: Build Rich-based TUI with thread awareness.

**Key features**:
- Show email context (sender, subject, date, attachments)
- Detect and display thread relationships
- Render HTML emails as readable text
- Record skip decisions as negative training examples

## Remaining Gaps / Decisions

1. **llm-archivist upgrade path**: When workflow count grows or classification accuracy needs improvement, enable llm-archivist. Requires:
   - PostgreSQL with pgvector extension
   - OpenAI API key for embeddings
   - Add `"classifier": {"enabled": true}` to config.json

2. **LLM classifier**: Config has `llm.enabled: false`. Can be enabled for complex classification scenarios. Costs money per classification.

3. **Gate classifier**: Config includes `classifier.gate_enabled` but gate logic for "worth archiving" is stubbed.

4. **Slack/File connectors**: Not yet integrated. Current focus is email.

## Next Steps

1. **Use the system**: Process emails to build training data with proper features
2. **Monitor classification quality**: If accuracy is poor with more workflows, consider llm-archivist
3. **Document Maildir usage**: Add instructions for `~/Mail/entity` structure
4. **Expand tests**: Add integration tests for Maildir fetch pipelines

## Summary

- mailflow is ready for interactive email processing with classification and archive storage
- Similarity classifier is the primary classifier (fixed feature extraction, clean training data)
- llm-archivist integration exists but is disabled (upgrade path for scale)
- Rich TUI provides good UX for workflow selection with thread context
- 236 tests pass
