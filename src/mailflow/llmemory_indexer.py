"""llmemory indexing integration for mailflow.

Indexes archived documents to llmemory for search after archive writes.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


async def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes.

    Args:
        pdf_bytes: PDF file content as bytes

    Returns:
        Extracted text content
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF not installed, cannot extract PDF text")
        return ""

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return "\n".join(text_parts)
    except Exception as e:
        logger.warning(f"Failed to extract text from PDF: {e}")
        return ""


async def extract_text_from_content(content: bytes, mimetype: str) -> str:
    """Extract searchable text from content based on mimetype.

    Args:
        content: File content as bytes
        mimetype: MIME type of the content

    Returns:
        Extracted text suitable for indexing
    """
    if mimetype == "application/pdf":
        return await extract_text_from_pdf(content)

    elif mimetype in ("text/plain", "text/markdown", "text/html"):
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("latin-1", errors="replace")

    else:
        logger.debug(f"No text extraction for mimetype: {mimetype}")
        return ""


async def index_to_llmemory(
    config,
    entity: str,
    document_id: str,
    document_name: str,
    document_type: str,
    content: bytes,
    mimetype: str,
    created_at: datetime,
    metadata_path: Path,
    origin: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Index a document to llmemory after archive write.

    Args:
        config: Mailflow Config object
        entity: Entity identifier (e.g., 'jro')
        document_id: Archive-protocol document_id (id_at_origin for llmemory)
        document_name: Human-readable document name
        document_type: Document type (e.g., 'email', 'document', 'attachment')
        content: Document content bytes
        mimetype: MIME type of content
        created_at: Document creation timestamp
        metadata_path: Path to the sidecar metadata JSON file
        origin: Optional origin metadata

    Returns:
        Dict with indexing results or None if indexing was skipped/failed
    """
    # Check if llmemory is configured
    if not config.has_llmemory_config():
        logger.debug("llmemory not configured, skipping indexing")
        return None

    # Extract text for indexing
    text = await extract_text_from_content(content, mimetype)
    if not text or not text.strip():
        logger.info(f"No text extracted from {document_name}, skipping indexing")
        return None

    try:
        from llmemory import LLMemory

        # Create llmemory instance
        database_url = config.get_llmemory_database_url()
        llmemory = LLMemory(connection_string=database_url)

        await llmemory.initialize()

        try:
            # Map document_type to llmemory DocumentType
            from llmemory.models import DocumentType
            type_mapping = {
                "email": DocumentType.EMAIL,
                "document": DocumentType.DOCUMENT,
                "attachment": DocumentType.DOCUMENT,
                "invoice": DocumentType.INVOICE,
                "receipt": DocumentType.RECEIPT,
                "contract": DocumentType.CONTRACT,
            }
            llm_doc_type = type_mapping.get(document_type.lower(), DocumentType.OTHER)

            # Build metadata for llmemory
            llm_metadata = {
                "source": "mail",
                "mimetype": mimetype,
            }
            if origin:
                llm_metadata["origin"] = origin

            # Add document to llmemory
            result = await llmemory.add_document(
                owner_id=entity,
                id_at_origin=document_id,
                document_name=document_name,
                document_type=llm_doc_type,
                content=text,
                document_date=created_at,
                metadata=llm_metadata,
            )

            # Update sidecar with llmemory info
            llmemory_info = {
                "indexed_at": datetime.now(timezone.utc).isoformat(),
                "document_id": str(result.document.document_id),
                "chunks_created": result.chunks_created,
                "embedding_model": llmemory.config.embedding.default_model,
                "embedding_provider": llmemory.config.embedding.default_provider,
            }

            _update_sidecar_llmemory(metadata_path, llmemory_info)

            logger.info(
                f"Indexed {document_name} to llmemory: "
                f"{result.chunks_created} chunks, {result.embeddings_created} embeddings"
            )

            return {
                "document_id": str(result.document.document_id),
                "chunks_created": result.chunks_created,
                "embeddings_created": result.embeddings_created,
                "processing_time_ms": result.processing_time_ms,
            }

        finally:
            await llmemory.close()

    except ImportError:
        logger.warning("llmemory package not installed, skipping indexing")
        return None
    except Exception as e:
        logger.error(f"Failed to index {document_name} to llmemory: {e}")
        # Don't fail the archive write, just log the error
        return None


def _update_sidecar_llmemory(metadata_path: Path, llmemory_info: dict[str, Any]) -> None:
    """Update the sidecar metadata file with llmemory indexing info.

    Args:
        metadata_path: Path to the metadata JSON file
        llmemory_info: Dict with llmemory indexing results
    """
    try:
        # Read existing metadata
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        # Update llmemory section
        metadata["llmemory"] = llmemory_info

        # Write back atomically
        temp_path = metadata_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, default=str)

        temp_path.replace(metadata_path)
        logger.debug(f"Updated sidecar with llmemory info: {metadata_path}")

    except Exception as e:
        logger.warning(f"Failed to update sidecar with llmemory info: {e}")
