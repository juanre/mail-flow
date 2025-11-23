# Naming and Normalization Rules

## Normalized Document Names (docs/)
- Pattern: `yyyy-mm-dd-normalised-file-name.(pdf|csv)`
- Steps:
  - Lowercase
  - Trim
  - Replace spaces with `-`
  - Remove characters not in `[a-z0-9._-]`
  - Collapse multiple dashes
  - Truncate base name to 120 chars (keep extension)
  - Ensure uniqueness within the year dir by appending `-2`, `-3`, …

## Originals (originals/)
- Preserve original filename and extension.
- Optional: prepend `yyyy-mm-dd-` for chronological sorting.
- One-to-one mapping to normalized doc via metadata (documents row includes original path in origin_json).

## Dates
- Prefer source date (email Date, Slack message ts, file mtime). Fallback to ingest time.
- All dates stored in UTC ISO.

## Streams
- Slack: `streams/slack/{channel}/yyyy/yyyy-mm-dd-transcript.md`
- Email: `streams/email/{mailbox-or-tag}/yyyy/yyyy-mm-dd-thread.md`
- Transcripts use relative links to docs: `../../../../docs/yyyy/yyyy-mm-dd-….[pdf|csv]`

## Collisions and Dedup
- Deduplicate by content hash; do not overwrite existing docs. Create `-2` variants for true duplicates from different sources.
- Keep originals even when normalized docs collide; tie-break by suffixing the normalized name.

