## Slack Ingestion Architecture and Implementation Plan

### Objectives
- **Archive**: Keep a local, searchable archive of all Slack messages and attachments, per entity.
- **Format**: Store transcripts in markdown (not orgmode). Keep raw JSON for fidelity.
- **Files**: Download and store attached files; create canonical local paths; index their text where possible.
- **Memory**: Index transcripts and files into llmemory when enabled.
- **Extensibility**: Reuse ingestion for Google Docs (produce .md and .pdf) and local documents.

## Scope (Phase 1 → Phase 3)
- **Phase 1 (MVP)**: Slack fetch, per-channel/day markdown transcript, raw JSON, attachment downloads, basic text extraction for .md/.txt/.pdf, optional llmemory indexing.
- **Phase 2**: Incremental sync across all conversations, threads support, Google Docs link detection (pass-through stub), robust rate limiting/backoff, CLI parity with `contextual` UX.
- **Phase 3**: Google Docs adapter (export .md/.pdf), Local docs adapter, parallelized safe downloads, tests and docs.

## Directory Layout
Base directory (configurable): `~/Documents/pmail/slack/{entity}/`

- `auth/user_token` — Slack user/bot token (xoxp-/xoxb-)
- `raw/{channel}/YYYY-MM-DD-{channel}.json` — raw message batches per day
- `md/{channel}/YYYY-MM-DD-{channel}.md` — markdown transcript per day
- `attachments/{channel}/YYYY-MM-DD-<sanitized-title>.<ext>` — downloaded files

Notes:
- Channel folder name uses sanitized channel name. DMs use `dm-<username>`. MPDMs use `mpdm-<id>`.
- All paths created atomically; filenames are date-prefixed and sanitized.

## Configuration
Add a `slack` section to `~/.pmail/config.json` (reuses existing config loader):

```json
{
  "slack": {
    "base_dir": "~/Documents/pmail/slack",
    "entities": {
      "jro": { "token_path": "~/.pmail/slack/jro/user_token" }
    },
    "ignore_channels": [],
    "rate_limit_min_interval_secs": 1
  },
  "llmemory": {
    "enabled": false,
    "connection_string": "",
    "owner_id": "default-owner",
    "embedding_provider": null,
    "openai_api_key": null
  }
}
```

Token placement per entity:
- `~/.pmail/slack/{entity}/user_token` (file content is the Slack token)

Required OAuth scopes (user or bot):
- `channels:history`, `channels:read`, `groups:history`, `groups:read`, `im:history`, `im:read`, `mpim:history`, `mpim:read`, `users:read`, `team:read`, `files:read`.

## Data Model and Metadata
- Transcript metadata (frontmatter-like in markdown):
  - Title: Slack Channel, Date
  - Workspace domain, channel id
- Message entry:
  - Username, ISO timestamp, permalink, thread_ts when present
  - Message text with resolved `@user` mentions
  - Attachments section (links to local canonical files)
- Attachment metadata (for memory):
  - `channel`, `slack_file_id`, `permalink`, `created_ts`, `mime`, `file_hash`, `relative_path`

## Processing Flow
1. Resolve entity configuration; init Slack WebClient.
2. Discover conversation(s): list by types `public_channel, private_channel, im, mpim`.
3. Determine cutoff `oldest` timestamp:
   - If `--force-full` then none; else compute latest from existing `raw/{channel}/*-{channel}.json`.
   - `--since` overrides with max(`since`, found_latest + epsilon).
4. Fetch history in pages (limit 200), respect rate limits/backoff.
5. For each message batch:
   - Resolve user map and workspace domain.
   - Buffer messages by day; fetch thread replies for thread parents.
6. For each day:
   - Ensure all attachments are downloaded to `attachments/{channel}` with deterministic filenames.
   - Write markdown transcript to `md/{channel}/YYYY-MM-DD-{channel}.md`.
   - Write raw JSON to `raw/{channel}/YYYY-MM-DD-{channel}.json`.
   - If llmemory enabled: index transcript, then index each attachment with extracted text where available.

### Incremental Sync
- Scan JSON files per channel to compute latest `ts` (float) across messages and replies.
- Store small per-channel state file later for O(1) resume (Phase 3 optional).

## Markdown Format
- File header:
  - `# Slack Channel: <channel>`
  - `Date: YYYY-MM-DD`
- Message block:
  - `## <display_name> — 2025-08-13T10:22:33-05:00`
  - `Permalink: https://<workspace>.slack.com/archives/<channel>/p<ts>`
  - Message text (mentions replaced to `@username`)
  - `### Attachments` (when present) with `- [title](../../attachments/<channel>/<file>)`
  - Replies as nested `### Reply by …` blocks in time order

## CLI
Add `pmail slack` command with options:
- `--entity <id>` (required)
- `--info` list channels/users and workspace domain
- `--channel <name|C…>` sync a single channel by name or id
- `--dm <username>` sync a DM conversation
- `--since <YYYY-MM-DD|unix_ts>` cutoff
- `--force-full` ignore incremental state
- `--include-archived` include archived channels in listing
- `--ignore-channels a,b,c` skip by name
- `--debug`, `--silent`

## Modules and Responsibilities
- `pmail/slack/client.py` — token loading, WebClient creation, API helpers (history, replies, users, channels, workspace info).
- `pmail/slack/storage.py` — directory resolution, filename normalization, atomic writes (JSON/MD), attachment saving with hashing and collision handling.
- `pmail/slack/markdown.py` — render message trees to markdown, resolve mentions, build permalinks.
- `pmail/slack/ingest.py` — orchestrate fetch → store → index; incremental sync.
- `pmail/text_extract.py` — minimal text extraction for `.md/.txt` and `.pdf`.
- `pmail/cli.py` — register `slack` command and options.

## Attachment Handling
- Prefer `url_private_download`, fallback `url_private` with `Authorization: Bearer <token>`.
- Filename rule: `YYYY-MM-DD-<normalized-title-or-name>.<ext>`; include short hash on collision.
- Google Docs detection (Phase 2/3): URLs containing `docs.google.com/document/` handled by GoogleDocsAdapter to produce `.md` and `.pdf`, returning canonical local paths used in transcript links.

## Memory Indexing
- Reuse `~/.pmail/config.json.llmemory` settings. Index only when `enabled == true`.
- Transcripts:
  - `DocumentType.CHAT`, `id_at_origin` = relative path to markdown.
  - Content = filtered markdown (header stripped), metadata: `relative_path`, `channel`, `workspace`, `date`, `file_hash`.
- Attachments:
  - If text extracted: `DocumentType.PDF` for `.pdf`, else `DocumentType.TEXT`.
  - `id_at_origin` = relative path; metadata includes Slack and file details.
- De-dupe via `file_hash`; if unchanged, skip.

## Error Handling and Rate Limiting
- Exponential backoff on Slack API errors; obey `Retry-After`.
- Min-interval throttling (configurable) between API calls.
- Robust logging: missing scopes, permission errors, DM user resolution fallback.
- Atomic writes to prevent partial files; temp downloads then move.

## Security
- Sanitize all filenames; validate output paths under configured base_dir.
- Do not log tokens; read tokens from files with restrictive perms.

## Dependencies
- Add to project dependencies:
  - `slack_sdk`
  - `requests`
  - `pypdf` (for PDF text extraction)

## Testing Strategy
- Unit tests:
  - Markdown rendering (mentions, permalinks, threads, attachments).
  - Filename normalization and collisions.
  - Incremental cutoff computation from JSON fixtures.
  - Text extraction for `.md`, `.txt`, `.pdf`.
- Integration tests (mock Slack API):
  - Channel history with threads, attachments, and pagination.
  - DM resolution flow.
  - Rate limit/backoff behavior.
- Manual runbook:
  - `pmail slack --entity jro --channel general --since 2025-01-01`.
  - Verify output folders and llmemory entries (if enabled).

## Timeline and Tasks
1. Scaffolding and config
   - Add config section, token loader, base directory resolver.
2. Client + storage + markdown
   - Implement `client.py`, `storage.py`, `markdown.py`; write transcripts and JSON.
3. Attachments
   - Download/save; basic text extraction; link in transcripts.
4. Ingestion orchestration + CLI
   - `ingest.py` incremental sync; register `pmail slack` command.
5. llmemory indexing (guarded by config)
   - Index transcripts and attachments; de-dupe by hash.
6. Tests + docs
   - Unit/integration tests; README/usage docs.

## Acceptance Criteria
- Running `pmail slack --entity <id> --channel <name> --since <date>`:
  - Creates `raw/` JSON and `md/` transcript files per day.
  - Downloads all referenced attachments to `attachments/` with sanitized, date-prefixed filenames.
  - Transcripts include message text, permalinks, attachments, and threaded replies in order.
  - When `llmemory.enabled=true`, both transcripts and attachments are searchable via `pmail msearch`.
  - Re-running with the same date range is idempotent and incremental (no duplicates; unchanged files not re-indexed).

## Future Work
- Google Docs adapter: export `.md`/`.pdf` and canonicalize links from Slack attachments.
- Local docs adapter: folder ingestion into canonical structure + memory.
- Per-channel state files for faster resume.
- Parallelized downloads with concurrency limits.
- Optional SQLite metadata for Slack files similar to `pmail` PDFs.


