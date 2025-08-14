from __future__ import annotations

import hashlib
import re
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from pmail.security import sanitize_filename, validate_path
from pmail.utils import atomic_json_write, atomic_write


def normalize_name(name: str) -> str:
    base = sanitize_filename(name)
    # enforce lowercase and collapse repeats of '-'
    base = re.sub(r"-+", "-", base.lower())
    return base


class SlackArchivePaths:
    def __init__(self, base_dir: str, entity: str, channel_name: str):
        base = validate_path(base_dir, allowed_base_dirs=[os.path.expanduser("~"), base_dir])
        self.entity = sanitize_filename(entity)
        self.channel = normalize_name(channel_name)
        self.root = base / self.entity
        self.raw_dir = self.root / "raw" / self.channel
        self.md_dir = self.root / "md" / self.channel
        self.attach_dir = self.root / "attachments" / self.channel
        for d in [self.raw_dir, self.md_dir, self.attach_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def json_path_for(self, date_str: str) -> Path:
        return self.raw_dir / f"{date_str}-{self.channel}.json"

    def md_path_for(self, date_str: str) -> Path:
        return self.md_dir / f"{date_str}-{self.channel}.md"

    def attachment_path(self, timestamp: datetime, title_or_name: str, ext: str) -> Path:
        date_prefix = timestamp.strftime("%Y-%m-%d")
        title = normalize_name(title_or_name) or "file"
        ext = (ext or "").lower()
        if ext and not ext.startswith("."):
            ext = "." + ext
        candidate = self.attach_dir / f"{date_prefix}-{title}{ext}"
        if not candidate.exists():
            return candidate
        # add short hash disambiguator
        h = hashlib.sha256(f"{timestamp.isoformat()}-{title}".encode("utf-8")).hexdigest()[:8]
        return self.attach_dir / f"{date_prefix}-{title}-{h}{ext}"


def compute_latest_ts(existing_json_files: Iterable[Path]) -> float:
    latest = 0.0
    import json

    for fp in existing_json_files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            for msg in data:
                ts_s = float(msg.get("ts", 0))
                latest = max(latest, ts_s)
                for rep in msg.get("replies", []) or []:
                    latest = max(latest, float(rep.get("ts", 0)))
        except Exception:
            continue
    return latest


def write_json(path: Path, messages: List[Dict]) -> None:
    atomic_json_write(path, messages, indent=2, ensure_ascii=False)


def write_markdown(path: Path, header_lines: List[str], body: str) -> None:
    content = "\n".join(header_lines) + "\n\n" + body
    atomic_write(path, content)


