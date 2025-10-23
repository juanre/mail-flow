from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from mailflow.security import sanitize_filename, validate_path
from mailflow.utils import atomic_write


class DocsArchivePaths:
    def __init__(self, base_dir: str, entity: str):
        base = validate_path(base_dir, allowed_base_dirs=[os.path.expanduser("~"), base_dir])
        self.entity = sanitize_filename(entity)
        self.root = base / self.entity / "docs"
        self.md_dir = self.root / "md"
        self.pdf_dir = self.root / "pdf"
        for d in [self.md_dir, self.pdf_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def target_paths(self, timestamp: datetime, title: str) -> Tuple[Path, Path]:
        date_prefix = timestamp.strftime("%Y-%m-%d")
        name = sanitize_filename(title) or "document"
        md = self.md_dir / f"{date_prefix}-{name}.md"
        pdf = self.pdf_dir / f"{date_prefix}-{name}.pdf"
        # Avoid collisions by adding a short hash if exists
        if md.exists() or pdf.exists():
            h = hashlib.sha256(f"{timestamp.isoformat()}-{name}".encode("utf-8")).hexdigest()[:8]
            md = self.md_dir / f"{date_prefix}-{name}-{h}.md"
            pdf = self.pdf_dir / f"{date_prefix}-{name}-{h}.pdf"
        return md, pdf


def write_md(path: Path, content: str) -> None:
    atomic_write(path, content)


def write_pdf(path: Path, content: bytes) -> None:
    # atomic write using bytes
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(content)
        f.flush()
    tmp.replace(path)


