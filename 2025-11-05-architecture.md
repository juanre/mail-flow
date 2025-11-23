# Unified Classification Architecture (2025-11-05)

This document defines a repository layout and component design where mailflow excels at email, a shared File Classifier handles documents from any source, and search/indexing remain global.

## Goals
- Keep mailflow focused on email workflows and learning.
- Use a single, teachable File Classifier for files from email, Slack, and filesystem.
- Make documents the canonical searchable unit; streams link to documents.
- Keep indexes global; storage is per-entity.

## Repository Layout
- {entity}/
  - docs/
    - yyyy/
      - yyyy-mm-dd-normalised-file-name.pdf
      - yyyy-mm-dd-normalised-file-name.csv
  - originals/
    - yyyy/
      - [optional yyyy-mm-dd-]Original File Name.ext (no normalization; original bytes)
  - streams/
    - slack/{channel}/yyyy/yyyy-mm-dd-transcript.md
    - email/{mailbox-or-tag}/yyyy/yyyy-mm-dd-thread.md (optional; only for “worth archiving” mails)
- indexes/
  - metadata.db (global, authoritative catalog)
  - fts.db (global SQLite FTS5)
  - llmemory_checkpoints/ (optional semantic indexer state)
- tmp/ (staging)

Notes
- No entities/ wrapper; entity is the top-level directory name. Indexes remain global.
- Transcripts use markdown with relative links to corresponding docs in `{entity}/docs/...`.

## Naming & Normalization
- docs: `yyyy-mm-dd-normalised-file-name.(pdf|csv)`
  - normalize: lowercase, spaces→`-`, strip non `[a-z0-9.-]`, collapse dashes, max 120 chars; ensure uniqueness via `-2`, `-3` suffix.
- originals: preserve original filename; optionally prepend `yyyy-mm-dd-` for ordering.
- Date source: email date, slack message date, or file mtime (UTC). Fallback to ingest time.

## Metadata Schema (indexes/metadata.db)
- documents(id, entity, date, filename, rel_path, hash, size, type[pdf|csv], source[email|slack|fs], workflow, category, confidence, origin_json, structured_json)
- streams(id, entity, kind[slack|email], channel_or_mailbox, date, rel_path, origin_json)
- links(stream_id, document_id)  // transcript → docs
- training(id, modality[email|file|slack], features_json, label_workflow, accepted, timestamp)
- dedup(hash UNIQUE, source_id, first_seen)

FTS (fts.db)
- Virtual tables indexing `filename`, `search_content`, `email_subject/from`, etc. Maintained by indexer.

## Components
- Connectors
  - mailflow (email): extracts features; evaluates Gate (worth archiving?).
    - If attachments: convert each to PDF/CSV → File Classifier → store docs; link from optional stream.
    - If no attachments and Gate=YES: render email→PDF → File Classifier → store doc; optional email stream.
  - fileflow (filesystem): convert→classify→store.
  - slackstash (Slack): store daily transcripts; files convert→classify→store; transcript links to docs.
- File Converter: deterministic conversion to PDF/CSV; originals stored separately.
- File Classifier (shared, teachable): classify(document, metadata, context)→{workflow, type, category, structured, confidence}.
- Gate Classifier (binary): decides if an email thread is “worth archiving”. Can reuse the same training store.
- Indexers: scan `{entity}/docs` and `{entity}/streams` to update `metadata.db` and `fts.db`; optional llmemory indexer for semantic search.
- Search CLI/API: unified query across global FTS and optional llmemory with filters: `--entity`, `--source`, `--channel`, `--workflow`, `--date`, `--type`.

## Invariants
- Every stored doc has: normalized doc name in `docs/`, original bytes in `originals/`, and a row in `documents`.
- Transcripts in `streams/` do not duplicate content; they link to `documents` via `links`.
- All operations are idempotent; dedup by content hash and source id.

## Next Steps
1) Finalize SQL schema and invariants; stub helpers in archive-protocol.
2) Define File Classifier interface + feature schemas (email, file, slack).
3) Adapt mailflow to call File Classifier; add Gate for thread archiving.
4) Implement indexers and link-writing conventions for transcripts.
5) Add global search CLI with filters; optional llmemory integration.
