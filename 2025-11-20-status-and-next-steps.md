# Status and Next Steps (2025-11-20)

## Current Status

### Architecture & Storage
- **Repository layout (v2) is adopted**: `{entity}/docs/{YYYY}/yyyy-mm-dd-name.pdf|csv`, `streams/<channel>/<yyyy>/<yyyy-mm-dd-transcript.md>`, and global indexes stored outside per-entity data.
- **Archive integration**: Workflows use `archive-protocol` to write documents, convert emails to PDF, and optionally convert attachments (text→PDF, TSV→CSV). Originals can be saved with optional date prefixes.
- **Global indexing/search**: `mailflow index` builds metadata/FTS SQLite databases; `mailflow gsearch` queries with filters (`--entity --workflow --source --category --limit`). Indexer docs live in `docs/indexer/`.

### Classification & Learning
- **llm-archivist integration** (enabled by default, Python ≥3.12):
  - Adapters build text+metadata and workflows for llm-archivist; results populate UI suggestions.
  - User confirmations send feedback to llm-archivist (stored decisions + optional Postgres/pgvector embeddings).
  - Dry-run mode trains mailflow + llm-archivist without executing workflows or marking emails processed.
- **Local training**: Each confirmed workflow is stored as a `CriteriaInstance`. Similarity engine reranks using Jaccard tokens; optional `file-classifier-core` provides per-attachment hints.
- **Configuration**: README documents full classifier setup (DB, env, bootstrap via `uv run llm-archivist metrics`).

### CLI & Workflows
- **Workflow creation**: `uv run mailflow init` and `setup-workflows` build workflows; UI supports creating on-the-fly with templates. Latest README explains customizing workflows and the need to keep names `{entity}-{doc}`.
- **Fetch commands**: `uv run mailflow fetch gmail …` (Gmail API) and `uv run mailflow fetch files …` (directories or Maildir). New Maildir discovery supports mailbox roots like `~/Mail/juan-gsk`.
- **Dry run**: `--dry-run` on file/gmail fetch avoids writes while training classifiers.
- **Logging and UI**: WorkflowSelector displays classifier suggestions (llm-archivist when available, otherwise hybrid similarity/LLM).

### Repo & Dependencies
- **Python version**: Requires Python 3.12+.
- **Local deps**: `llm-archivist`, `archive-protocol`, `file-classifier-core`, `llmring`, `pgdbm`. README includes `uv sync` instructions.
- **Tests**: `uv run pytest` (213 tests) pass; integration points for llm-archivist verified separately.

## Remaining Gaps / Decisions
1. **Production llm-archivist DB**: Needs provisioning (Postgres, pgvector). README outlines steps but DB/role creation is manual. Verify migrations and vector extension in the target environment.
2. **Attachment classifier feedback**: mailflow records per-email decisions to llm-archivist, but attachments still use `file-classifier-core`. Decide whether to replace with llm-archivist or keep dual systems.
3. **Gate classifier**: Config includes `classifier.gate_enabled` but gate logic for "worth archiving" is stubbed. Implement actual gating using llm-archivist workflows (e.g., `archive` vs `ignore`).
4. **Slack/File connectors**: Not yet integrated. Current focus is email; separate repos handle Slack (mailflow-memory) and file classification.
5. **Docs & automation**: Consider adding a dedicated how-to for running dry-run → production, and scripts for seeding sample workflows.

## Next Steps for Successor
1. **Provision & test llm-archivist in production mode**
   - Create Postgres DB + role; ensure pgvector installed.
   - Set env (`ARCHIVIST_USE_DB=1`, `DATABASE_URL=…`, `OPENAI_API_KEY=…`).
   - Run `uv run llm-archivist metrics` to apply migrations.
   - Execute a dry-run on a Maildir (e.g., `uv run mailflow fetch files ~/Mail/juan-gsk --dry-run`) and confirm decisions appear in llm-archivist DB.
2. **Implement gate classifier (optional)**
   - Define workflows `["archive", "ignore"]` in llm-archivist.
   - Before running archival workflows, query llm-archivist to decide whether to store or skip (persist decision for audit).
   - Expose config flags to enable/disable gating per entity.
3. **Document Maildir usage**
   - Update README/Docs with Maildir instructions and samples (e.g., `~/Mail/juan-gsk` structure).
   - Add a note about permissions for Dropbox-backed mail stores (since symlink points outside repo).
4. **Expand tests for file fetch**
   - Add integration tests using sample Maildir (temp dir) to ensure fetch pipelines run end-to-end.
   - Include a test verifying dry-run doesn’t call `RepositoryWriter`.
5. **Plan Slack/file pipeline integration** (if in scope)
   - Coordinate with mailflow-memory or context of file classifier.
   - Ensure storage naming matches `docs/specs/naming-and-normalization.md`.
6. **Automation/CI**
   - Add CI job to run `uv sync` + `uv run pytest` (Python 3.12/3.13).
   - Optionally include `uv run llm-archivist test` with env gating.

## Summary for Incoming Developer
- mailflow is feature-complete for interactive email processing with classification, archive storage, and global search.
- llm-archivist is integrated; user confirmations now train both systems (dry-run supported).
- Next tasks center on production deployment (DB, LLM env), gating optional workflows, and extending connectors.
- Review README (Installation & Classifier sections) for environment setup, and run `uv run mailflow init` to create base workflows before testing.
