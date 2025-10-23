# Connectors-Oriented Memory Architecture (2025-10-23)

## Motivation

The existing `mailflow` branch blends email processing with Slack, Google Docs, and other ingestion logic inside a single application. While convenient, this coupling introduces several challenges:

- **Growing footprint** – every mailflow install ships Playwright, Slack SDK, Google APIs, llmemory, etc., even if the user only needs email workflows.
- **Tight coupling** – changes in Slack or Docs ingestion can inadvertently impact the email pipeline or its dependencies.
- **Operational inflexibility** – it is difficult to run ingestion flows on different machines or schedules; everything must execute through the mailflow CLI.
- **Limited extensibility** – adding new sources (Teams, Jira, local file sync) requires modifying mailflow itself.

To keep mailflow excellent at email while enabling broader “memory” capabilities, we propose a **connector-based architecture**: independent ingestion services feed a shared repository with consistent metadata; indexing and search operate over that repository rather than on per-application internals.

## High-Level Architecture

```
[mailflow workflows] --\
[slack ingestor] -----+--> RepositoryWriter --> ~/Archive/entities/... --> Indexers --> Search/UI
[gdocs exporter] -----/
[localdocs sync] ----/
```

The system has five layers:

1. **Connectors** – purpose-built ingest tools (mailflow, Slack, GDocs, local docs, custom sources) that produce content plus metadata.
2. **RepositoryWriter library** – shared utilities that normalize paths, compute hashes, emit metadata JSON, and append to optional manifests.
3. **Shared Repository** – a directory tree under `~/Archive/` organized by entity, workflow, and source, with consistent content and metadata placement.
4. **Indexers** – batch or streaming jobs that read metadata and update llmemory, SQLite FTS, or other search backends.
5. **Consumers** – CLIs or UIs that query the indexes and optionally read metadata/content directly.

## Shared Repository Layout

```
~/Archive/
  manifest.jsonl                  # optional append-only change stream
  entities/
    {entity}/
      workflows/                  # Classified documents from any source
        {workflow}/               # e.g., jro-expense, jro-invoice, jro-tax-doc
          {YYYY}/
            {YYYY}-{MM}-{DD}-{source}-{filename}.pdf
            {YYYY}-{MM}-{DD}-{source}-{filename}-attachment.png
      streams/                    # Unclassified message/conversation streams
        slack/
          {channel}/{YYYY}/
            {YYYY}-{MM}-{DD}.md
            {YYYY}-{MM}-{DD}.json
        mail/
          raw/{YYYY}/
            {YYYY}-{MM}-{DD}-{message-id}.eml (optional)
      metadata/
        workflows/{workflow}/{YYYY}/
          {YYYY}-{MM}-{DD}-{source}-{filename}.json
        streams/
          slack/{channel}/{YYYY}/
            {YYYY}-{MM}-{DD}.json
          mail/raw/{YYYY}/
            {YYYY}-{MM}-{DD}-{message-id}.json
      indexes/
        fts.sqlite
        llmemory_checkpoints/
```

**Key principles**

- **workflows/** contains classified documents from any source, organized by workflow to preserve business semantics (receipts, invoices, tax documents)
- **streams/** contains unclassified message/conversation streams organized by source (Slack channels, raw emails)
- Single-level year directories (yyyy/) with self-documenting filenames (yyyy-mm-dd-source-...) make files easy to browse and copy
- Source prefix in filenames (mail-, localdocs-, slack-) enables filtering while keeping workflow-centric organization
- Metadata JSON sidecars mirror the workflows/ and streams/ structure
- To find all jro expenses: browse workflows/jro-expense/; to find all from mail: filter by filename prefix

## Metadata Schema

A single JSON schema governs all connectors. An example for mail-sourced documents:

```jsonc
{
  "id": "mail=jro-expense/2025-10-23T13:45:01Z/sha256:abc...",
  "entity": "jro",
  "source": "mail",
  "workflow": "jro-expense",
  "type": "document",
  "subtype": "receipt",
  "created_at": "2025-10-23T13:45:01Z",
  "origin": {
    "mail": {
      "message_id": "<message-id>",
      "subject": "Receipt from Acme",
      "from": "billing@acme.com",
      "to": ["juan@juanreyero.com"],
      "date": "2025-10-23T13:44:57Z",
      "workflow_name": "jro-expense",
      "confidence_score": 0.91,
      "attachment_filename": "acme_receipt.pdf",
      "headers": { "x-original-to": "..." }
    }
  },
  "content": {
    "path": "../workflows/jro-expense/2025/2025-10-23-mail-acme-receipt.pdf",
    "hash": "sha256:abc...",
    "size_bytes": 123456,
    "mimetype": "application/pdf",
    "attachments": [
      "../workflows/jro-expense/2025/2025-10-23-mail-acme-receipt-logo.png"
    ]
  },
  "tags": ["workflow:jro-expense", "mail", "receipt"],
  "relationships": [
    {
      "type": "derived_from_email",
      "target_id": "mail=raw/2025-10-23T13:45:01Z/sha256:def..."
    }
  ],
  "ingest": {
    "connector": "mailflow@0.4.0",
    "ingested_at": "2025-10-23T13:45:05Z",
    "hostname": "laptop",
    "workflow_run_id": "uuid"
  },
  "llmemory": {
    "indexed_at": null,
    "embedding_model": null,
    "embedding_id": null
  }
}
```

Slack, GDocs, and localdocs populate the `origin.{source}` section with their own fields (channel, doc ID, source path, etc.). All connectors share these top-level keys: `id`, `entity`, `source`, `workflow` (when applicable), `type`, `created_at`, `content`, `tags`, `relationships`, `ingest`, and optional `llmemory` info.

## Connectors

### Mailflow (email workflows)

- Continues to provide the CLI/UI for processing email and choosing workflows.
- When a workflow runs (e.g., `save_pdf`, `save_attachment`), mailflow calls `RepositoryWriter.write_document()` with:
  - `entity` (parsed from workflow name, e.g., "jro" from "jro-expense")
  - `workflow_name` (e.g., "jro-expense")
  - `source` = "mail"
  - content bytes/paths
  - origin metadata (message headers, workflow output)
  - attachments information
- `RepositoryWriter` writes classified documents to `workflows/{workflow}/{YYYY}/{YYYY}-{MM}-{DD}-mail-...` and emits metadata under `metadata/workflows/{workflow}/{YYYY}/{YYYY}-{MM}-{DD}-mail-....json`.
- `processed_emails_tracker` records the metadata `id` to maintain idempotency.
- Optional raw email storage in `streams/mail/raw/{YYYY}/{YYYY}-{MM}-{DD}-{message-id}.eml` preserves `.eml` files for legal/audit needs (stored in streams/ since they're unclassified).

### Slack Ingestor

- Standalone service/CLI (`slack-ingestor sync --entity jro --channel general`).
- Fetches message history, renders Markdown per day, saves raw JSON per day.
- **Message transcripts** go to `streams/slack/{channel}/{YYYY}/{YYYY}-{MM}-{DD}.md` (unclassified conversation streams).
- **Attachments** can be classified:
  - If attachment can be mapped to a workflow (e.g., PDF shared in #expenses channel), classify as "jro-expense"
  - Write to `workflows/jro-expense/{YYYY}/{YYYY}-{MM}-{DD}-slack-{filename}.pdf`
  - Metadata includes channel, message timestamp, user who shared it
  - If attachment cannot be classified, store in `streams/slack/{channel}/attachments/`
- Metadata references channel, timestamps, user IDs, thread context, etc.

### Google Docs Exporter

- Standalone service using the Drive API.
- Exports `.md` and `.pdf` with classification:
  - If doc can be mapped to a workflow (via folder, title pattern, or manual rules), write to `workflows/{workflow}/{YYYY}/{YYYY}-{MM}-{DD}-gdocs-{doc-title}.pdf`
  - If unclassified, could store in `streams/gdocs/` or skip (TBD based on use case)
- Metadata includes doc ID, title, modified time, owners, URL, folder path, etc.

### Local Docs Synchronizer

- Watches or periodically scans directories for document ingestion.
- Classifies documents to workflows based on:
  - Source directory path (e.g., `~/Downloads/receipts/` → jro-expense)
  - Filename patterns
  - Manual classification UI
- Writes classified docs to `workflows/{workflow}/{YYYY}/{YYYY}-{MM}-{DD}-localdocs-{filename}`
- Metadata stores original path, hashes, timestamps, and classification confidence
- Can respect `.mlignore`-style filters to avoid noise.

### Additional Connectors

- Provide a small SDK (in Python first) that exposes:
  - `RepositoryWriter`
  - `MetadataBuilder`
  - Schema validation utilities
- Encourage external contributors to implement new connectors (e.g., Jira, Notion exports) without modifying mailflow.

## RepositoryWriter Library

Responsibilities:

- Resolve target directories based on entity + source + workflow.
- Sanitize filenames, handle collisions via content hashes, and create year subdirectories.
- Generate self-documenting filenames with yyyy-mm-dd- prefix for easy browsing.
- Write content atomically (tmp → rename) and compute SHA-256 hashes.
- Serialize metadata, enforce required fields, and write alongside content.
- Optionally append the same JSON record to `manifest.jsonl` for downstream streaming consumers.
- Provide helpers for linking multiple files under a single metadata record (e.g., PDF + text preview + attachments).

This library is the shared "plumbing" that keeps connectors consistent.

## Indexing & Search

1. **Memory Indexer**
   - Periodically scans repository metadata for entries where `llmemory.indexed_at == null`.
   - Extracts text (from content or precomputed snippets), pushes to llmemory along with metadata fields, then updates the metadata (or writes a companion status file).
2. **SQLite/FTS Index**
   - Maintained per entity for fast keyword search.
   - Stores metadata fields like `workflow`, `type`, tags, created_at, etc.
3. **UI/CLI**
   - Supports queries such as “show jro’s receipts in October”, “find Slack messages mentioning invoice #12345”, or “search all sources for Acme contract”.

## Advantages

- **Tight mailflow focus** – mailflow specializes in email workflows without inheriting non-email dependencies.
- **Modularity** – connectors run independently (different hosts, schedules, permission scopes).
- **Extensibility** – new sources plug in via a documented schema instead of touching mailflow internals.
- **Observability** – metadata and manifests provide a full audit trail.
- **Workflow-centric organization** – all classified documents (regardless of source) live together in workflow-specific folders, making it easy to browse all jro expenses in one place.
- **Source transparency** – filename prefixes (mail-, slack-, localdocs-) preserve source information while enabling workflow-first browsing.

## Implementation Plan

1. **Schema & Library**
   - Finalize JSON schema and directory naming rules.
   - Implement `RepositoryWriter` and `RepositoryConfig` packages (Python module shared by connectors).
2. **Mailflow Refactor**
   - Replace current filesystem writes with `RepositoryWriter` calls.
   - Map current workflow directories (e.g., `~/Documents/mailflow/jro/expense`) to new repo structure (`~/Archive/entities/jro/workflows/jro-expense/YYYY/YYYY-MM-DD-mail-...`).
   - Update filename generation to use yyyy-mm-dd-{source}- prefix format.
   - Ensure attachments, metadata, and processed tracker align with the new IDs.
   - Parse entity from workflow name (jro-expense → entity: jro).
3. **Connector Extraction**
   - Move Slack and GDocs ingestion into separate packages/services; reuse code but trim mailflow dependencies.
   - Provide CLI wrappers (`slack-ingestor`, `gdocs-ingestor`) and sample configs.
4. **Indexer Service**
   - Implement llmemory/FTS indexer as an independent job referencing metadata.
   - Add CLI for manual re-indexing and status checks.
5. **Documentation & Tooling**
   - Publish repository structure docs, quickstart scripts, and backup recommendations.
   - Offer repository validation and reporting utilities.

## Conclusion

By separating ingestion connectors from mailflow and converging on a shared repository with rich metadata, we retain mailflow's strengths in email automation while enabling a scalable "memory" platform.

The **workflows/** and **streams/** distinction provides clarity:
- Workflows contain classified documents from any source, organized by business purpose (receipts, invoices, tax documents)
- Streams contain unclassified message/conversation flows, organized by source and channel

Self-documenting filenames (yyyy-mm-dd-source-...) enable both workflow-centric browsing ("all jro expenses") and source filtering ("all from mail") without complex tooling. The architecture supports future connectors, clearer deployment models, flexible indexing, and a consistent view of knowledge across all sources.


