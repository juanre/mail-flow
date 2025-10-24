# Integrating archive-protocol into mailflow

## Current State

**mailflow** writes directly to filesystem:
- Path: `~/Documents/mailflow/{entity}/{doc_type}/`
- Metadata: SQLite FTS database per directory
- Filenames: `{date}-{from}-{subject}.pdf`

## Target State

**mailflow** uses archive-protocol:
- Path: `~/Archive/entities/{entity}/workflows/{workflow}/{YYYY}/`
- Metadata: JSON sidecars (archive-protocol format)
- Filenames: `{YYYY}-{MM}-{DD}-mail-{subject}.pdf`
- SQLite FTS: Deprecated (llmemory will handle search)

## Changes Required

### 1. Configuration (config.py)

Add archive settings to defaults:
```python
"archive": {
    "enabled": True,           # Use archive-protocol
    "base_path": "~/Archive"   # Repository base path
}
```

Add to required_keys validation.

### 2. Entity Parser (utils.py)

Add utility function:
```python
def parse_entity_from_workflow(workflow_name: str) -> str:
    """Parse entity from workflow name.

    Examples:
        jro-expense → jro
        tsm-invoice → tsm
        gsk-tax-doc → gsk

    Args:
        workflow_name: Workflow name (entity-doctype format)

    Returns:
        Entity identifier

    Raises:
        ValueError: If workflow name doesn't follow entity-doctype pattern
    """
    parts = workflow_name.split('-', 1)
    if len(parts) < 2:
        raise ValueError(
            f"Invalid workflow name: {workflow_name}. "
            "Expected format: entity-doctype (e.g., jro-expense)"
        )

    entity = parts[0]

    # Validate entity format
    if not entity.islower() or not entity.isalnum():
        raise ValueError(f"Invalid entity in workflow name: {entity}")

    return entity
```

### 3. Workflow Functions (workflow.py)

Refactor all workflow functions to use RepositoryWriter:

**Before (save_pdf):**
```python
def save_pdf(message: dict, directory: str, filename_template: str) -> int:
    # Find PDFs or convert email
    output_path = directory / filename
    save_email_as_pdf(message, output_path, ...)

    # Store in metadata
    metadata_store.store_pdf_metadata(...)
```

**After (save_pdf):**
```python
def save_pdf(message: dict, workflow: str, config: Config) -> dict:
    # Parse entity
    entity = parse_entity_from_workflow(workflow)

    # Initialize writer
    from archive_protocol import RepositoryWriter, RepositoryConfig
    archive_config = RepositoryConfig(
        base_path=config.settings["archive"]["base_path"]
    )
    writer = RepositoryWriter(
        config=archive_config,
        entity=entity,
        source="mail"
    )

    # Convert email to PDF bytes
    pdf_bytes = convert_email_to_pdf_bytes(message, ...)

    # Write using archive-protocol
    document_id, content_path, metadata_path = writer.write_document(
        workflow=workflow,
        content=pdf_bytes,
        mimetype="application/pdf",
        origin={
            "message_id": message["Message-ID"],
            "subject": message["Subject"],
            "from": message["From"],
            "to": message["To"],
            "date": message["Date"],
            "workflow_name": workflow,
            "confidence_score": message.get("_confidence_score")
        },
        document_type="receipt",  # or classify dynamically
        original_filename=f"{message['Subject']}.pdf"
    )

    return {
        "document_id": document_id,
        "content_path": str(content_path),
        "metadata_path": str(metadata_path)
    }
```

### 4. PDF Converter Changes

**Current:** `save_email_as_pdf(message, output_path, ...)`
Writes directly to file.

**New:** Split into two functions:
- `convert_email_to_pdf_bytes(message, ...) -> bytes` - Returns PDF bytes
- `save_email_as_pdf(message, output_path, ...)` - Kept for backward compat

This allows workflow.py to get bytes and pass to RepositoryWriter.

### 5. Attachment Handler Changes

**Current:** `save_attachments_from_message()` writes to directory directly

**New:** Return attachment bytes instead:
- `extract_attachments(message) -> list[tuple[str, bytes, str]]` - Returns (filename, content, mimetype)
- Then workflow.py passes to RepositoryWriter with attachments parameter

### 6. Update Default Paths

**UI (ui.py):**
```python
# Old
typical=["~/Documents/mailflow/jro/expense", ...]

# New
typical=["~/Archive/entities/jro/workflows/jro-expense", ...]
```

**CLI init (cli.py):**
```python
# Old
directory=f"~/Documents/mailflow/{entity_code}/{doc_code}"

# New
directory=f"~/Archive/entities/{entity_code}/workflows/{entity_code}-{doc_code}"
```

### 7. Metadata Store Transition

**Phase 1 (Now):**
- Keep metadata_store.py for backward compatibility
- New writes go through archive-protocol
- Old searches still work

**Phase 2 (Later):**
- Remove metadata_store.py
- All search via llmemory
- Migrate old metadata to archive-protocol format

### 8. Tests

Update tests to:
- Expect new directory structure
- Verify archive-protocol metadata files
- Check workflows/{workflow}/{YYYY}/ paths
- Validate metadata JSON format

## Implementation Order

**Step 1:** Add config and utilities (non-breaking)
- Add archive config section
- Add parse_entity_from_workflow()
- Tests for entity parsing

**Step 2:** Refactor PDF converter (preparation)
- Add convert_email_to_pdf_bytes()
- Keep save_email_as_pdf() for compat
- Tests

**Step 3:** Refactor attachment handler (preparation)
- Add extract_attachments()
- Keep save_attachments_from_message() for compat
- Tests

**Step 4:** Refactor workflow.py (main change)
- Update save_pdf() to use RepositoryWriter
- Update save_attachment() to use RepositoryWriter
- Update save_email_pdf() to use RepositoryWriter
- Tests

**Step 5:** Update UI and CLI paths
- Update default directory suggestions
- Update init command
- Tests

**Step 6:** Integration testing
- End-to-end test processing emails
- Verify archive structure created
- Verify metadata correct
- Verify backward compat works

## Testing Strategy

**For each refactored function:**
1. Write test showing new behavior (archive-protocol structure)
2. Update existing tests to expect new paths
3. Verify old tests still pass (backward compat)

**Integration test:**
```python
def test_email_to_archive_protocol(temp_config_dir):
    """Test email processing creates archive-protocol structure."""
    config = Config(config_dir=temp_config_dir)
    config.settings["archive"] = {
        "enabled": True,
        "base_path": str(temp_config_dir / "archive")
    }

    # Process email
    result = save_pdf(sample_email, workflow="jro-expense", config=config)

    # Verify structure
    archive_base = Path(temp_config_dir) / "archive" / "entities" / "jro"

    # Check workflows directory
    workflows_dir = archive_base / "workflows" / "jro-expense"
    assert workflows_dir.exists()

    # Check year subdirectory
    year_dir = workflows_dir / "2025"
    assert year_dir.exists()

    # Check files
    pdf_files = list(year_dir.glob("2025-*-mail-*.pdf"))
    assert len(pdf_files) == 1

    # Check metadata
    metadata_dir = archive_base / "metadata" / "workflows" / "jro-expense" / "2025"
    json_files = list(metadata_dir.glob("2025-*-mail-*.json"))
    assert len(json_files) == 1

    # Validate metadata format
    import json
    with open(json_files[0]) as f:
        metadata = json.load(f)

    assert metadata["entity"] == "jro"
    assert metadata["source"] == "mail"
    assert metadata["workflow"] == "jro-expense"
    assert "origin" in metadata
    assert "mail" in metadata["origin"]
```

## Backward Compatibility

**Keep working during transition:**
- If `archive.enabled = False`, use old code path
- If `archive.enabled = True`, use archive-protocol
- Default to True for new installs
- Existing users can migrate gradually

## Rollout Plan

1. **Merge to feature branch** - Don't break main
2. **Test thoroughly** - All 206+ tests pass
3. **Document migration** - Update README
4. **Merge to main** - When confident
5. **Update docs** - New users get archive-protocol by default

## Success Criteria

✅ All existing tests pass
✅ New archive structure created correctly
✅ Metadata format matches archive-protocol schema
✅ Can browse workflows/{workflow}/{YYYY}/ in Finder
✅ Entity parsing works correctly
✅ Filenames have yyyy-mm-dd-mail- format
✅ Integration with future llmemory clear

Ready to implement?
