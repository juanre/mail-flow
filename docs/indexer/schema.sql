-- Global index schema for Unified Classification Architecture (2025-11-05)
-- Authoritative catalog lives in indexes/metadata.db; lexical FTS in indexes/fts.db

-- documents: one row per archived document (PDF/CSV)
CREATE TABLE IF NOT EXISTS documents (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  entity           TEXT       NOT NULL,
  date             TEXT       NOT NULL,             -- ISO 8601 (UTC) yyyy-mm-dd or full timestamp
  filename         TEXT       NOT NULL,             -- normalized filename (with extension)
  rel_path         TEXT       NOT NULL,             -- path relative to {entity}/ (e.g., docs/2025/2025-11-05-invoice.pdf)
  hash             TEXT       NOT NULL,             -- SHA256 of content
  size             INTEGER    NOT NULL,
  type             TEXT       NOT NULL,             -- 'pdf' | 'csv'
  source           TEXT       NOT NULL,             -- 'email' | 'slack' | 'fs'
  workflow         TEXT,                             -- classifier label
  category         TEXT,                             -- broad category (expense, tax, ...)
  confidence       REAL,
  origin_json      TEXT       NOT NULL,             -- JSON with source-specific fields
  structured_json  TEXT                              -- JSON extracted info/metadata
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_documents_hash ON documents(hash);
CREATE INDEX IF NOT EXISTS ix_documents_entity_date ON documents(entity, date);
CREATE INDEX IF NOT EXISTS ix_documents_workflow ON documents(workflow);
CREATE INDEX IF NOT EXISTS ix_documents_source ON documents(source);

-- streams: one row per transcript/thread page (slack/email)
CREATE TABLE IF NOT EXISTS streams (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  entity             TEXT    NOT NULL,
  kind               TEXT    NOT NULL,           -- 'slack' | 'email'
  channel_or_mailbox TEXT    NOT NULL,
  date               TEXT    NOT NULL,
  rel_path           TEXT    NOT NULL,           -- e.g., streams/slack/general/2025/2025-11-05-transcript.md
  origin_json        TEXT    NOT NULL            -- JSON with workspace, message ids, participants, etc.
);

CREATE INDEX IF NOT EXISTS ix_streams_entity_date ON streams(entity, date);
CREATE INDEX IF NOT EXISTS ix_streams_kind_channel ON streams(kind, channel_or_mailbox);

-- links: many-to-many between streams and documents
CREATE TABLE IF NOT EXISTS links (
  stream_id   INTEGER NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  PRIMARY KEY (stream_id, document_id)
);

-- training: shared training store for all modalities
CREATE TABLE IF NOT EXISTS training (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  modality       TEXT    NOT NULL,         -- 'email' | 'file' | 'slack'
  features_json  TEXT    NOT NULL,
  label_workflow TEXT    NOT NULL,
  accepted       INTEGER NOT NULL DEFAULT 1,
  timestamp      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_training_modality ON training(modality);
CREATE INDEX IF NOT EXISTS ix_training_label ON training(label_workflow);

-- dedup: record of seen content/source identifiers
CREATE TABLE IF NOT EXISTS dedup (
  hash       TEXT NOT NULL,
  source_id  TEXT,                 -- message-id, slack_file_id, filepath, etc.
  first_seen TEXT NOT NULL,
  PRIMARY KEY (hash)
);

-- FTS (in fts.db): virtual tables linked by rowid to documents.id
-- Example:
-- CREATE VIRTUAL TABLE pdf_search USING fts5(filename, email_subject, email_from, search_content, content='');
-- Application guarantees rowid alignment and maintains entries on upsert/delete.

