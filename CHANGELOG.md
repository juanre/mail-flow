## 0.3.0

**LLM Integration & Deduplication**

- Added LLM-powered email classification using llmring (optional, opt-in)
- Hybrid classification: similarity-based with LLM fallback for ambiguous cases
- Confidence-based routing: high confidence uses similarity (free), low confidence uses LLM
- Deduplication system: tracks processed emails by message-id and content hash
- Batch processing: `pmail batch` command for processing directories
- CLI options: `--llm`, `--llm-model`, `--force` flags
- Cost warnings and estimates for LLM usage
- Input sanitization and workflow validation for LLM responses
- Upgraded to Python 3.11+ (required for llmring)
- llmring.lock with model alias bindings (fast/balanced/deep)
- Comprehensive LLM configuration and validation
- 124 tests (30 new tests with real LLM API calls, no mocks)
- Updated documentation: removed outdated design docs, consolidated examples

## 0.2.0

- Fixed FTS5 search: align `pdf_search.rowid` with `pdf_metadata.id`, use `bm25(pdf_search)` for ranking, and return recent PDFs when query is empty
- Added default workflows (`save-attachments`, `save-receipts`, `archive`)
- Config now creates `workflows`, `history`, and `backups` directories and exposes `backup_file`
- Attachment handling: correct size from decoded payload; store `pdf_original_filename`
- Similarity features include `to` address for `to_address` weighting
- Console logging level now reflects configured level; `readline` fallback when `gnureadline` is unavailable
- README fix for repository path; moved `black` and `pytest` to dev deps


