"""mailflow MCP Server (STDIO)

Exposes read-only tools over MCP so an MCP-enabled LLM can query the
mailflow archive without changing local/Gmail flows.

Tools provided:
- search_pdfs: search across configured/base directories
- get_pdf_metadata: retrieve full metadata for a PDF by path or filename
- get_pdf_text_preview: retrieve a short text preview for a PDF/email

Usage:
  uv run mailflow-mcp  # starts STDIO server
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_server import MCPServer
from mcp_server.transport import StdioServerTransport

from mailflow.config import Config
from mailflow.models import DataStore
from mailflow.metadata_store import MetadataStore
from mailflow.security import validate_path

logger = logging.getLogger(__name__)


def _collect_base_dirs(config: Config) -> List[Path]:
    """Collect likely base directories for PDF archives.

    Sources:
      - Directories from save_pdf workflows
      - Common defaults (~/Documents/mailflow, ~/receipts)
    """
    data_store = DataStore(config)
    base_dirs: set[Path] = set()
    for workflow in data_store.workflows.values():
        if workflow.action_type == "save_pdf" and "directory" in workflow.action_params:
            base_dirs.add(Path(workflow.action_params["directory"]).expanduser())
    base_dirs.add(Path("~/Documents/mailflow").expanduser())
    base_dirs.add(Path("~/receipts").expanduser())
    return sorted(d for d in base_dirs if d.exists())


def _get_store_for_dirs(base_dirs: List[Path]) -> List[MetadataStore]:
    stores: List[MetadataStore] = []
    for base in base_dirs:
        try:
            stores.append(MetadataStore(str(base)))
        except Exception:
            continue
    return stores


def _validate_base_dir(user_dir: Optional[str], config: Config) -> Optional[Path]:
    if not user_dir:
        return None
    allowed = [os.path.expanduser(p) for p in config.settings.get("security", {}).get("allowed_directories", ["~"])]
    try:
        return validate_path(user_dir, allowed_base_dirs=allowed)
    except Exception:
        return None


def create_server() -> MCPServer:
    server = MCPServer(name="mailflow-mcp", version="1.0.0")
    config = Config()

    async def search_pdfs(query: Optional[str] = None, limit: int = 20, directory: Optional[str] = None, type: Optional[str] = None) -> List[Dict[str, Any]]:  # noqa: A002 - param name 'type'
        base_dir = _validate_base_dir(directory, config)
        stores: List[MetadataStore]
        if base_dir:
            stores = [MetadataStore(str(base_dir))]
        else:
            stores = _get_store_for_dirs(_collect_base_dirs(config))

        all_results: List[Dict[str, Any]] = []
        for store in stores:
            try:
                if type:
                    results = store.search_by_type(type, limit)
                else:
                    results = store.search(query or "", limit)
                all_results.extend(results)
            except Exception:
                continue

        # Deduplicate by (email_message_id, filename), then trim to limit
        seen = set()
        unique: List[Dict[str, Any]] = []
        for r in all_results:
            key = (r.get("email_message_id"), r.get("filename"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(r)
            if len(unique) >= limit:
                break
        return unique

    server.register_tool(
        name="search_pdfs",
        handler=search_pdfs,
        description="Search PDFs in the archive by text or document type",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search text (use empty for recent)"},
                "limit": {"type": "integer", "default": 20},
                "directory": {"type": "string", "description": "Base directory to search"},
                "type": {"type": "string", "description": "Document type filter (invoice, receipt, tax, etc.)"},
            },
        },
    )

    async def get_pdf_metadata(filepath_or_name: str, directory: Optional[str] = None) -> Optional[Dict[str, Any]]:
        base_dir = _validate_base_dir(directory, config)
        base_dirs = [base_dir] if base_dir else _collect_base_dirs(config)
        for base in base_dirs:
            try:
                store = MetadataStore(str(base))
                result = store.get_by_filepath(filepath_or_name)
                if result:
                    # Avoid leaking large fields unnecessarily; return as-is
                    return result
            except Exception:
                continue
        return None

    server.register_tool(
        name="get_pdf_metadata",
        handler=get_pdf_metadata,
        description="Get full metadata record for a PDF by filepath or filename",
        input_schema={
            "type": "object",
            "properties": {
                "filepath_or_name": {"type": "string"},
                "directory": {"type": "string", "description": "Base directory to search"},
            },
            "required": ["filepath_or_name"],
        },
    )

    async def get_pdf_text_preview(filepath_or_name: str, directory: Optional[str] = None, max_chars: int = 1000) -> Optional[str]:
        base_dir = _validate_base_dir(directory, config)
        base_dirs = [base_dir] if base_dir else _collect_base_dirs(config)
        for base in base_dirs:
            try:
                store = MetadataStore(str(base))
                result = store.get_by_filepath(filepath_or_name)
                if not result:
                    continue
                text = result.get("pdf_text_content") or result.get("email_body_text") or ""
                text = (text or "").strip()
                if not text:
                    return None
                if len(text) > max_chars:
                    return text[:max_chars] + "..."
                return text
            except Exception:
                continue
        return None

    server.register_tool(
        name="get_pdf_text_preview",
        handler=get_pdf_text_preview,
        description="Get a short text preview for a PDF (or email body if converted)",
        input_schema={
            "type": "object",
            "properties": {
                "filepath_or_name": {"type": "string"},
                "directory": {"type": "string"},
                "max_chars": {"type": "integer", "default": 1000},
            },
            "required": ["filepath_or_name"],
        },
    )

    return server


def main():  # pragma: no cover - thin wrapper
    logging.basicConfig(level=logging.INFO)
    server = create_server()

    async def run():
        transport = StdioServerTransport()
        await server.run(transport)

    asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    main()


