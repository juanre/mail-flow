# Indexer Contract (metadata + FTS)

Purpose: define how indexers populate global indexes (`indexes/metadata.db`, `indexes/fts.db`) from `{entity}/docs` and `{entity}/streams`.

## Responsibilities
- Scan entity roots, detect new/changed docs and streams.
- Populate `documents`, `streams`, and `links` tables idempotently.
- Maintain FTS entries with rowid alignment to `documents.id`.
- Resolve transcript links to documents and fill `links` table.

## Inputs
- Filesystem view:
  - Docs: `{entity}/docs/yyyy/yyyy-mm-dd-*.pdf|csv`
  - Originals: `{entity}/originals/yyyy/[yyyy-mm-dd-]Original.ext`
  - Streams:
    - Slack: `{entity}/streams/slack/{channel}/yyyy/yyyy-mm-dd-transcript.md`
    - Email: `{entity}/streams/email/{mailbox}/yyyy/yyyy-mm-dd-thread.md`
- Extraction helpers:
  - Text extraction (PDF/CSV → text preview)
  - Origin metadata parsers (from sidecars or embedded headers if present)

## Outputs
- documents row per doc; `rel_path` is path relative to `{entity}/`.
- streams row per transcript/thread.
- links: resolve markdown links in streams to documents by normalized relative path.
- FTS rows with fields: filename, email_subject, email_from, search_content.

## Idempotency & Consistency
- Upsert by `hash` for documents; update size/date as needed.
- Recompute and upsert FTS entry on content change.
- On delete: remove `documents` row and its FTS row; cascade deletes `links`.
- Ensure `pdf_search.rowid == documents.id` when inserting/updating FTS.

## Error Handling
- Partial failures never corrupt indexes: use transactions, retry with exponential backoff.
- Keep a minimal checkpoint (last scan times per entity/channel) to bound re-scan cost.

## Security
- Path validation and normalization; never follow symlinks outside entity root.
- Size caps for text extraction to avoid memory spikes.

