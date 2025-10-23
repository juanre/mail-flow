"""Minimal text extraction helpers for transcripts and attachments."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(p.strip() for p in parts if p)
    except Exception:
        return ""


def best_effort_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt", ".org"}:
        return read_text_file(path)
    if suffix == ".pdf":
        return extract_pdf_text(path)
    return ""


