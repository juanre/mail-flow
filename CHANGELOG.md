## 0.2.0

- Fixed FTS5 search: align `pdf_search.rowid` with `pdf_metadata.id`, use `bm25(pdf_search)` for ranking, and return recent PDFs when query is empty.
- Added default workflows (`save-attachments`, `save-receipts`, `archive`).
- Config now creates `workflows`, `history`, and `backups` directories and exposes `backup_file`.
- Attachment handling: correct size from decoded payload; store `pdf_original_filename`.
- Similarity features include `to` address for `to_address` weighting.
- Console logging level now reflects configured level; `readline` fallback when `gnureadline` is unavailable.
- README fix for repository path; moved `black` and `pytest` to dev deps.


