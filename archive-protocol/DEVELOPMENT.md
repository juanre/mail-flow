# Development Guide

## Coding Standards

This package follows the same standards as the parent mailflow project.

### Core Principles

**1. Doing it right is better than doing it fast**
- Never skip steps or take shortcuts
- Comprehensive error handling required
- All edge cases must be tested

**2. Test Driven Development (TDD)**
- Write failing test first
- Implement minimal code to pass
- Refactor while keeping tests green

**3. YAGNI - You Aren't Gonna Need It**
- Don't add features we don't need
- Keep it minimal (~500 lines)
- Resist feature creep

**4. Data Safety First**
- Atomic operations everywhere
- Never lose user data
- Proper error handling and recovery

### File Structure

**Every Python file must start with ABOUTME comments:**
```python
# ABOUTME: Brief description of what this file does
# ABOUTME: Additional context about how it works
```

### Naming Conventions

**Names tell WHAT code does, not HOW:**
- ✅ `RepositoryWriter` - writes to repository
- ❌ `AtomicFileWriter` - implementation detail
- ✅ `compute_hash()` - computes hash
- ❌ `compute_sha256_hash()` - algorithm detail

**Avoid temporal context:**
- ❌ `NewMetadataBuilder`
- ❌ `ImprovedWriter`
- ✅ `MetadataBuilder`

### Error Handling

**All errors must:**
1. Use custom exception hierarchy (ArchiveError, ValidationError, WriteError, PathError)
2. Include recovery hints when possible
3. Log before raising
4. Clean up resources on failure

**Example:**
```python
try:
    write_atomically(path, content)
except Exception as e:
    logger.error(f"Failed to write {path}: {e}")
    # Cleanup
    if temp_file.exists():
        temp_file.unlink()
    raise WriteError(
        f"Failed to write document: {e}",
        recovery_hint="Check disk space and permissions"
    )
```

### Testing Requirements

**All code must have tests:**
- Unit tests for all public functions
- Integration tests for workflows
- Edge case tests (empty input, huge input, invalid input)
- Error condition tests

**Test quality:**
- Use real data, not mocked behavior
- Test actual file operations with cleanup
- Verify atomic operations
- Check resource cleanup

**Coverage requirements:**
- All public APIs: 100%
- Error paths: 100%
- Edge cases: Comprehensive

## Project Structure

```
archive-protocol/
├── src/archive_protocol/
│   ├── __init__.py           # Public API exports only
│   ├── writer.py             # RepositoryWriter (core functionality)
│   ├── metadata.py           # MetadataBuilder
│   ├── schema.py             # Pydantic models
│   ├── config.py             # Configuration
│   ├── utils.py              # Shared utilities
│   └── exceptions.py         # Exception hierarchy
├── tests/
│   ├── conftest.py           # Test fixtures
│   ├── test_writer.py        # RepositoryWriter tests
│   ├── test_metadata.py      # MetadataBuilder tests
│   ├── test_schema.py        # Schema validation tests
│   └── test_utils.py         # Utility tests
├── README.md                 # User documentation
├── ARCHITECTURE.md           # System design and vision
├── DEVELOPMENT.md            # This file
├── INTEGRATION.md            # Connector developer guide
└── pyproject.toml            # Package configuration
```

## Development Workflow

### Setup

```bash
# Clone
git clone <repo>
cd archive-protocol

# Install dependencies
uv sync

# Run tests
uv run pytest tests/ -v
```

### Making Changes

**1. Write test first:**
```python
# tests/test_writer.py
def test_new_feature():
    """Test description."""
    writer = RepositoryWriter(...)
    result = writer.new_method(...)
    assert result == expected
```

**2. Run test (should fail):**
```bash
uv run pytest tests/test_writer.py::test_new_feature -v
# FAILED - good, feature doesn't exist yet
```

**3. Implement minimal code:**
```python
# src/archive_protocol/writer.py
def new_method(self, ...):
    """Docstring with purpose."""
    # Minimal implementation
    return result
```

**4. Run test (should pass):**
```bash
uv run pytest tests/test_writer.py::test_new_feature -v
# PASSED - feature works
```

**5. Run full suite:**
```bash
uv run pytest tests/ -v
# All tests should still pass
```

**6. Refactor if needed**

**7. Commit**

### Adding Dependencies

**Never edit pyproject.toml manually for dependencies.**

Use uv commands:
```bash
# Add runtime dependency
uv add <package>

# Add dev dependency
uv add --dev <package>

# Check what changed
git diff pyproject.toml
```

### Code Review Checklist

Before committing, verify:
- [ ] All tests pass (105+)
- [ ] New code has tests
- [ ] ABOUTME comments present
- [ ] No hardcoded values (use config)
- [ ] Error handling comprehensive
- [ ] Resources cleaned up on failure
- [ ] Logging at appropriate levels
- [ ] Type hints on all functions
- [ ] Docstrings on public APIs
- [ ] No commented-out code
- [ ] No TODO/FIXME markers

## Security

### Input Validation

**All external input must be validated:**

```python
# Filenames
filename = sanitize_filename(user_input)  # Remove dangerous chars

# Entity/workflow names
if not re.match(r'^[a-z0-9_-]+$', entity):
    raise ValidationError("Invalid entity format")

# Content size
if len(content) > MAX_SIZE:
    raise ValidationError(f"Content too large: {len(content)} bytes")

# Hashes
if not hash_str.startswith("sha256:"):
    raise ValidationError("Invalid hash format")
```

### Path Safety

**Never trust user paths:**
- Use Path.resolve() to canonicalize
- Validate against allowed directories
- Check for path traversal attempts
- Sanitize all path components

### Atomic Operations

**All writes must be atomic:**
```python
# Correct pattern
temp_file = path.parent / f".tmp_{path.name}_{os.getpid()}"
with open(temp_file, "xb") as f:
    f.write(content)
    f.flush()
    os.fsync(f.fileno())
temp_file.rename(path)  # Atomic on same filesystem
```

**Never:**
```python
# Wrong - not atomic
with open(path, "wb") as f:
    f.write(content)
```

## Performance

### Avoid Common Pitfalls

**❌ Don't:**
- Load entire file into memory if not needed
- Use O(n²) algorithms
- Make unnecessary file I/O operations
- Compute hashes multiple times

**✅ Do:**
- Stream large files
- Use efficient data structures
- Cache expensive computations
- Batch operations when possible

### Benchmarks

Target performance:
- Write document: <50ms (excluding content hashing)
- Generate metadata: <5ms
- Sanitize filename: <1ms
- Compute hash (1MB file): <10ms

## Debugging

### Logging

Use Python's logging module:
```python
import logging
logger = logging.getLogger(__name__)

# Levels
logger.debug("Detailed trace")      # Implementation details
logger.info("Normal operation")     # Milestones
logger.warning("Degraded operation") # Recovered errors
logger.error("Operation failed")    # Data loss risk
```

### Common Issues

**1. Permission denied writing files**
- Check ~/Archive exists and is writable
- Check directory permissions (should be 0o755)

**2. Metadata validation fails**
- Check hash format: must be "sha256:hexdigest"
- Check entity/source/workflow: lowercase, alphanumeric + hyphens only
- Check required fields present

**3. Collision handling doesn't work**
- Verify content hash is computed correctly
- Check hash suffix extraction logic
- Verify counter increments

## Extending archive-protocol

### Adding New Features

**Follow this process:**

1. **Is it needed?** (YAGNI check)
   - Is this required by multiple connectors?
   - Or is it connector-specific?
   - Keep archive-protocol minimal

2. **Write RFC** (if significant change)
   - Describe problem and solution
   - Show examples
   - Get feedback before implementing

3. **Follow TDD**
   - Write tests first
   - Minimal implementation
   - Refactor

4. **Update documentation**
   - README examples
   - API reference
   - Integration guide

### Backward Compatibility

**Once published (v0.1.0), maintain compatibility:**
- Don't break existing connector code
- Deprecate, don't delete
- Add, don't change
- Version bumps follow semantic versioning

## Release Process

### Version Bumping

```bash
# Update version in pyproject.toml
# Update version in __init__.py
# Update CHANGELOG.md

# Tag release
git tag v0.1.0
git push --tags
```

### Checklist

- [ ] All tests pass
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] Version bumped
- [ ] No uncommitted changes
- [ ] README examples tested

## Questions?

For architecture questions, see ARCHITECTURE.md.
For integration questions, see INTEGRATION.md.
For usage examples, see README.md.
