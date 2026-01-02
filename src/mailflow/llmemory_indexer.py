"""llmemory indexing integration for mailflow.

Indexes archived documents to llmemory for search after archive writes.
Fail-fast: requires llmemory config when indexing is invoked.
"""

import asyncio
import concurrent.futures
import json
import logging
from pathlib import Path
from typing import Any

from mailflow.config import ConfigurationError

logger = logging.getLogger(__name__)


def run_indexing(
    config,
    entity: str,
    document_id: str,
    content_path: Path,
    metadata_path: Path,
) -> dict[str, Any]:
    """Run llmemory indexing from sync context.

    This handles the async/sync boundary properly, detecting whether
    there's already a running event loop and using appropriate strategy.

    Fail-fast: raises ConfigurationError if llmemory is not configured.

    Args:
        config: Mailflow Config object
        entity: Entity identifier (e.g., 'jro')
        document_id: Archive-protocol document_id (id_at_origin for llmemory)
        content_path: Path to the content file in the archive
        metadata_path: Path to the sidecar metadata JSON file

    Returns:
        Dict with indexing results

    Raises:
        ConfigurationError: If llmemory is not configured
    """
    coro = index_to_llmemory(
        config=config,
        entity=entity,
        document_id=document_id,
        content_path=content_path,
        metadata_path=metadata_path,
    )

    try:
        # Check if there's already a running event loop
        asyncio.get_running_loop()
        # We're in an async context - run in a separate thread
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # No running loop - safe to use asyncio.run()
        return asyncio.run(coro)


async def index_to_llmemory(
    config,
    entity: str,
    document_id: str,
    content_path: Path,
    metadata_path: Path,
) -> dict[str, Any]:
    """Index a document to llmemory after archive write.

    Uses llmemory's ArchiveIndexer for text extraction and indexing.
    Fail-fast: raises ConfigurationError if llmemory is not configured.

    Args:
        config: Mailflow Config object
        entity: Entity identifier (e.g., 'jro')
        document_id: Archive-protocol document_id (id_at_origin for llmemory)
        content_path: Path to the content file in the archive
        metadata_path: Path to the sidecar metadata JSON file

    Returns:
        Dict with indexing results

    Raises:
        ConfigurationError: If llmemory is not configured
        ImportError: If llmemory package is not installed
    """
    # Fail-fast: require llmemory configuration
    # This runs preflight which raises ConfigurationError if not configured
    database_url = config.get_llmemory_database_url()

    # Load sidecar to get metadata
    with open(metadata_path, "r", encoding="utf-8") as f:
        sidecar = json.load(f)

    # Import llmemory components
    from llmemory import ArchiveIndexer, ArchiveItem
    from llmemory.manager import MemoryManager

    # Create ArchiveItem from the archive paths
    # Get archive base path from config to compute relative path
    archive_base = Path(config.settings.get("archive", {}).get("base_path", "~/Archive")).expanduser()
    try:
        relative_path = str(content_path.relative_to(archive_base))
    except ValueError:
        # content_path is not under archive_base, use full path
        relative_path = str(content_path)

    item = ArchiveItem(
        content_path=content_path,
        sidecar_path=metadata_path,
        entity=entity,
        document_id=document_id,
        relative_path=relative_path,
        source=sidecar.get("source"),
        workflow=sidecar.get("workflow"),
        mimetype=sidecar.get("mimetype"),
        is_indexed=False,
    )

    # Create MemoryManager and ArchiveIndexer
    manager = await MemoryManager.create(connection_string=database_url)

    try:
        indexer = ArchiveIndexer(manager)
        result = await indexer.index_item(item)

        if not result.success:
            logger.warning(f"Failed to index {content_path}: {result.error}")
            return {
                "success": False,
                "error": result.error,
            }

        logger.info(
            f"Indexed {content_path.name} to llmemory: "
            f"{result.chunks_created} chunks"
        )

        return {
            "success": True,
            "document_id": result.document_id,
            "chunks_created": result.chunks_created,
        }

    finally:
        await manager.close()
