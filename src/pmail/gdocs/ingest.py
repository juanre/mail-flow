from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from pmail.config import Config
from pmail.gdocs.client import GoogleClient
from pmail.gdocs.storage import DocsArchivePaths, write_md, write_pdf
from pmail.security import validate_path
from pmail.text_extract import best_effort_text


DOC_URL_RE = re.compile(r"https?://docs\.google\.com/document/(?:u/\d+/)?d/([a-zA-Z0-9_-]+)")


def parse_doc_url(url: str) -> Optional[str]:
    m = DOC_URL_RE.search(url)
    return m.group(1) if m else None


def _base_dir(cfg: Config) -> str:
    s = cfg.settings.get("gdocs", {})
    return s.get("base_dir", "~/Documents/pmail")


def ingest_doc_url(cfg: Config, entity: str, url: str) -> Tuple[Path, Path]:
    file_id = parse_doc_url(url)
    if not file_id:
        raise ValueError("Invalid Google Docs URL")
    return ingest_doc_id(cfg, entity, file_id)


def ingest_doc_id(cfg: Config, entity: str, file_id: str) -> Tuple[Path, Path]:
    client = GoogleClient()
    meta = client.file_metadata(file_id)
    title = meta.get("name", file_id)
    ts_str = meta.get("modifiedTime") or meta.get("createdTime")
    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")) if ts_str else datetime.utcnow()

    import os
    base_root = validate_path(_base_dir(cfg), allowed_base_dirs=[os.path.expanduser("~"), _base_dir(cfg)])
    paths = DocsArchivePaths(_base_dir(cfg), entity)
    md_path, pdf_path = paths.target_paths(ts, title)

    # export markdown and pdf
    md_bytes = client.export_markdown(file_id)
    pdf_bytes = client.export_pdf(file_id)
    write_md(md_path, md_bytes.decode("utf-8", errors="ignore"))
    write_pdf(pdf_path, pdf_bytes)

    # Optional: index
    llm_cfg = cfg.settings.get("llmemory", {})
    if llm_cfg.get("enabled"):
        from pmail.slack.ingest import index_memory_if_enabled

        rel_md = md_path.relative_to(base_root)
        text = best_effort_text(md_path)
        index_memory_if_enabled(
            cfg,
            base_root,
            rel_md,
            text,
            {"document_type": "google_doc", "title": title, "date": ts.strftime("%Y-%m-%d")},
        )
        rel_pdf = pdf_path.relative_to(base_root)
        # For PDFs, text extraction is optional and may be empty; still index metadata via md
    return md_path, pdf_path


def ingest_drive_folder(cfg: Config, entity: str, folder_id: str, since_iso: Optional[str] = None) -> int:
    client = GoogleClient()
    # List files in the folder; only Google Docs documents
    q = f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.document' and trashed = false"
    if since_iso:
        q += f" and modifiedTime > '{since_iso}'"
    files = client.drive.files().list(q=q, fields="files(id,name,modifiedTime)").execute().get("files", [])
    count = 0
    for f in files:
        try:
            ingest_doc_id(cfg, entity, f["id"])
            count += 1
        except Exception:
            continue
    return count


