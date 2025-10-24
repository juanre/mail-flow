# Changelog

All notable changes to archive-protocol will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Year-based subdirectory organization for workflows and streams
  - Content files now stored in `workflows/{workflow}/{YYYY}/` instead of `workflows/{workflow}/`
  - Stream files now stored in `streams/{stream}/{YYYY}/` instead of `streams/{stream}/`
  - Metadata directories mirror content structure with same year subdirectories
- Timezone-aware datetime handling in document ID generation
  - Timezone-aware datetimes are automatically converted to UTC
  - Naive datetimes are assumed to be UTC (as before)
- Comprehensive error cleanup for attachment writes
  - If attachment write fails, all previously written attachments are cleaned up
  - Prevents orphaned attachment files

### Changed
- **BREAKING**: Removed manifest feature entirely
  - Removed `enable_manifest` config parameter
  - Removed `_append_to_manifest()` method
  - No longer generates `manifest.jsonl` files
  - Filesystem metadata files are the single source of truth
  - Rationale: YAGNI - manifest was redundant and added complexity without clear benefit
- **BREAKING**: `RepositoryWriter` initialization now requires explicit `config` and `source` parameters
  - Must pass `RepositoryConfig` object instead of `base_path` string
  - Must specify `source` parameter (e.g., "mail", "slack")
  - See README for updated examples
- Metadata directories are now created upfront during path resolution
  - Previously created lazily during first write
  - More consistent with documented behavior

### Fixed
- Fixed bare `except:` clause that could catch system exceptions
  - Changed to `except Exception:` to avoid catching KeyboardInterrupt/SystemExit
- Fixed timezone handling in document ID generation
  - Document IDs now correctly use UTC timezone regardless of input timezone
- Fixed README API examples to show correct initialization syntax
- Fixed attachment cleanup on partial failure
  - All written attachments are now removed if any attachment write fails

### Documentation
- Updated README.md with correct API examples throughout
- Updated all documentation to reflect year subdirectory structure
- Removed all manifest references from README, ARCHITECTURE, and INTEGRATION docs
- All code examples now show proper `RepositoryConfig` usage

### Internal
- Reduced test count from 108 to 105 tests (removed 3 manifest-specific tests)
- All 105 tests passing
- Reduced codebase by ~30 lines (manifest removal)

## [0.1.0] - 2025-10-24

### Added
- Initial production-ready release
- Core `RepositoryWriter` for writing documents and streams
- `MetadataBuilder` for generating consistent metadata
- `RepositoryConfig` for configuration management
- Pydantic-based metadata schema validation
- Atomic write operations with fsync
- SHA-256 content hashing
- Filename collision handling
- Support for attachments
- Comprehensive test suite (108 tests)
- Complete documentation (README, ARCHITECTURE, DEVELOPMENT, INTEGRATION)

### Features
- Write classified documents to workflows/
- Write unclassified streams to streams/
- Consistent metadata schema across all sources
- Self-documenting filenames (YYYY-MM-DD-source-timestamp)
- Entity-based repository organization
- Integration-ready for llmemory indexing

[Unreleased]: https://github.com/yourusername/archive-protocol/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourusername/archive-protocol/releases/tag/v0.1.0
