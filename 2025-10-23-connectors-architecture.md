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
      content/
        mail/
          {workflow}/             # e.g., jro-expense, jro-tax, jro-doc
            {YYYY}/
              {YYYY}-{MM}-{DD}-{filename}.pdf
              {YYYY}-{MM}-{DD}-{filename}-attachment.png
            raw_email/{YYYY}/
              {YYYY}-{MM}-{DD}-{message-id}.eml (optional)
        slack/
          {channel}/{YYYY}/
            {YYYY}-{MM}-{DD}.md
            {YYYY}-{MM}-{DD}.json
            {YYYY}-{MM}-{DD}-{attachment}
        gdocs/
          {folder_hint}/{YYYY}/
            {YYYY}-{MM}-{DD}-{doc-title}.pdf
        localdocs/
          {YYYY}/
            {YYYY}-{MM}-{DD}-{filename}
      metadata/
        mail/{workflow}/{YYYY}/
          {YYYY}-{MM}-{DD}-{filename}.json
        slack/{channel}/{YYYY}/
          {YYYY}-{MM}-{DD}.json
        gdocs/{YYYY}/
          {YYYY}-{MM}-{DD}-{doc-id}.json
        localdocs/{YYYY}/
          {YYYY}-{MM}-{DD}-{hash}.json
      indexes/
        fts.sqlite
        llmemory_checkpoints/
```

**Key principles**

- Content is organized per entity and per workflow (for mail) to preserve business semantics such as receipts, invoices, tax documents, etc.
- Single-level year directories (yyyy/) with self-documenting filenames (yyyy-mm-dd-...) make files easy to browse and copy
- Metadata JSON sidecars live alongside the content hierarchy, making it trivial to locate both data and provenance
- Other connectors (Slack, GDocs, localdocs) keep their content under separate namespaces but may set the `workflow` field in metadata when a mapping exists

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
    "path": "../content/mail/jro-expense/2025/2025-10-23-acme-receipt.pdf",
    "hash": "sha256:abc...",
    "size_bytes": 123456,
    "mimetype": "application/pdf",
    "attachments": [
      "../content/mail/jro-expense/2025/2025-10-23-acme-receipt-logo.png"
    ]
  },
  "tags": ["workflow:jro-expense", "mail", "receipt"],
  "relationships": [
    {
      "type": "derived_from_email",
      "target_id": "mail=email/2025-10-23T13:45:01Z/sha256:def..."
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
- When a workflow runs (e.g., `save_pdf`, `save_attachment`, custom actions), mailflow calls `RepositoryWriter.write_document()` with:
  - `entity`
  - `workflow_name`
  - content bytes/paths
  - origin metadata (message headers, workflow output)
  - attachments information
- `RepositoryWriter` writes to `content/mail/{workflow}/{YYYY}/{YYYY}-{MM}-{DD}-...` and emits metadata under `metadata/mail/{workflow}/{YYYY}/{YYYY}-{MM}-{DD}-....json`.
- `processed_emails_tracker` records the metadata `id` to maintain idempotency.
- Optional raw email storage (`raw_email/{YYYY}/{YYYY}-{MM}-{DD}-{message-id}.eml`) preserves `.eml` files for legal/audit needs.

### Slack Ingestor

- Standalone service/CLI (`slack-ingestor sync --entity jro --channel general`).
- Fetches history, renders Markdown per day, saves raw JSON per day, and downloads attachments.
- All files are saved under `content/slack/...`; metadata JSON references channel, timestamps, user IDs, etc.
- If transcripts correspond to a known workflow (e.g., a Slack channel dedicated to “jro-expense”), the metadata can set `workflow` and even place a copy under the workflow directory. Otherwise, it stays under Slack’s namespace.

### Google Docs Exporter

- Standalone service using the Drive API.
- Exports `.md` and `.pdf` to `content/gdocs/{folder_hint}/...`.
- Metadata includes doc ID, title, modified time, owners, URL, etc.
- Optional mapping rules can tag docs with workflows or copy them into workflow directories.

### Local Docs Synchronizer

- Watches or periodically scans directories.
- Copies or hard-links files into `content/localdocs/...`, storing original path, hashes, and timestamps in metadata.
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
- **Consistency** – workflows remain first-class concepts; mailflow’s document outputs live in workflow-specific folders per entity.

## Implementation Plan

1. **Schema & Library**
   - Finalize JSON schema and directory naming rules.
   - Implement `RepositoryWriter` and `RepositoryConfig` packages (Python module shared by connectors).
2. **Mailflow Refactor**
   - Replace current filesystem writes with `RepositoryWriter` calls.
   - Map current workflow directories (e.g., `~/Documents/mailflow/jro/expense`) to new repo structure (`~/Archive/entities/jro/content/mail/jro-expense/YYYY/YYYY-MM-DD-...`).
   - Update filename generation to use yyyy-mm-dd- prefix format.
   - Ensure attachments, metadata, and processed tracker align with the new IDs.
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

By separating ingestion connectors from mailflow and converging on a shared repository with rich metadata, we retain mailflow’s strengths in email automation while enabling a scalable “memory” platform. Workflow-specific directories remain intact for receipts, invoices, tax documents, and other classifications. The architecture supports future connectors, clearer deployment models, flexible indexing, and a consistent view of knowledge across all sources.


