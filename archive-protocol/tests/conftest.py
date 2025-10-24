# ABOUTME: Pytest fixtures for archive-protocol tests
# ABOUTME: Provides common test fixtures for repository, config, and sample data

from datetime import datetime
from pathlib import Path

import pytest

from archive_protocol.config import RepositoryConfig


@pytest.fixture
def temp_archive_dir(tmp_path):
    """Create temporary archive directory.

    Returns:
        Path to temporary archive directory
    """
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    return archive_dir


@pytest.fixture
def sample_config(temp_archive_dir):
    """Create sample RepositoryConfig for testing.

    Returns:
        RepositoryConfig instance with test settings
    """
    return RepositoryConfig(
        base_path=str(temp_archive_dir),
        enable_manifest=True,
        create_directories=True,
        atomic_writes=True,
        compute_hashes=True,
        hash_algorithm="sha256"
    )


@pytest.fixture
def sample_metadata():
    """Create sample metadata dictionary for testing.

    Returns:
        Dictionary with valid metadata structure
    """
    return {
        "id": "mail=expenses/2025-10-23T14:30:00Z/sha256:abc123def456" + "0" * 52,
        "entity": "test-entity",
        "source": "mail",
        "workflow": "expenses",
        "type": "receipt",
        "subtype": "digital",
        "created_at": datetime(2025, 10, 23, 14, 30, 0).isoformat(),
        "content": {
            "path": "content.pdf",
            "hash": "sha256:abc123def456" + "0" * 52,
            "size_bytes": 1024,
            "mimetype": "application/pdf",
            "attachments": []
        },
        "origin": {
            "email_id": "12345",
            "subject": "Test Receipt",
            "from": "sender@example.com"
        },
        "tags": ["expense", "travel"],
        "relationships": [],
        "ingest": {
            "connector": "mail@1.0.0",
            "ingested_at": datetime(2025, 10, 23, 14, 35, 0).isoformat(),
            "hostname": "test-host",
            "workflow_run_id": None
        },
        "llmemory": {
            "indexed_at": None,
            "document_id": None,
            "chunks_created": None,
            "embedding_model": None,
            "embedding_provider": None
        }
    }


@pytest.fixture
def sample_content():
    """Create sample document content for testing.

    Returns:
        Bytes of sample content
    """
    return b"This is test document content for testing purposes."


@pytest.fixture
def sample_pdf_content():
    """Create sample PDF content for testing.

    Returns:
        Minimal valid PDF bytes
    """
    # Minimal valid PDF structure
    return b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test PDF) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000317 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
409
%%EOF
"""
