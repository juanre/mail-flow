from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime as dt
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from mailflow.config import Config
from mailflow.security import validate_path, sanitize_filename
from mailflow.slack.storage import SlackArchivePaths
from mailflow.slack.ingest import _base_dir
from mailflow.text_extract import best_effort_text


ORG_LINK_RE = re.compile(r"\[\[file:([^\]]+)\]\[([^\]]+)\]\]")
ORG_HEADER_RE = re.compile(r"^(\*+)\s+(.*)")


@dataclass
class OrgMessageMeta:
    timestamp: Optional[str] = None
    permalink: Optional[str] = None


def find_old_paths(old_root: Path) -> Tuple[Path, Path, Path]:
    """Guess old contextual paths: (org_dir, raw_json_dir, attach_dir)."""
    candidates = [
        (old_root / "slack", old_root / "raw" / "slack", old_root / "raw" / "slack" / "attachments"),
        (old_root / "context" / "slack", old_root / "raw" / "slack", old_root / "raw" / "slack" / "attachments"),
    ]
    for org_dir, raw_dir, att_dir in candidates:
        if org_dir.exists():
            return org_dir, raw_dir, att_dir
    # fallback to old_root as org_dir
    return old_root, old_root / "raw" / "slack", old_root / "raw" / "slack" / "attachments"


def parse_filename(file_path: Path) -> Tuple[str, str]:
    m = re.match(r"(\d{4}-\d{2}-\d{2})-(.+)\.org$", file_path.name)
    if not m:
        raise ValueError(f"Unrecognized filename: {file_path}")
    return m.group(1), m.group(2)


def resolve_source(old_org_dir: Path, old_raw_dir: Path, rel_path: str) -> Optional[Path]:
    rel = Path(rel_path)
    # Try raw/slack base (most likely)
    cand = (old_raw_dir / rel).resolve()
    if cand.exists():
        return cand
    # Try relative to org file root
    cand2 = (old_org_dir / rel).resolve()
    if cand2.exists():
        return cand2
    # Try relative to old_root
    try:
        cand3 = (old_org_dir.parent / rel).resolve()
        if cand3.exists():
            return cand3
    except Exception:
        pass
    return None


def convert_org_to_markdown(
    org_text: str,
    old_org_dir: Path,
    old_raw_dir: Path,
    new_paths: SlackArchivePaths,
    date_str: str,
) -> Tuple[str, List[Path]]:
    """Convert org to markdown; copy linked files into new attachments, return md body and list of copied files."""
    copied: List[Path] = []

    # First pass: collect and copy attachments
    link_map: Dict[str, str] = {}
    for m in ORG_LINK_RE.finditer(org_text):
        rel_path, title = m.group(1), m.group(2)
        src = resolve_source(old_org_dir, old_raw_dir, rel_path)
        if not src or not src.exists():
            continue
        # Destination filename with date prefix and sanitized title fallback
        title_part = sanitize_filename(title) or src.stem
        dest = new_paths.attachment_path(dt.strptime(date_str, "%Y-%m-%d"), title_part, src.suffix)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied.append(dest)
            # compute href relative to md dir root (md/<channel>) parent is md; we want path from md/<channel>
            href = dest.relative_to(new_paths.md_dir)
            # but our markdown renderer expects link relative to md dir; so use ../attachments/... path
            # Actually md file is new_paths.md_dir/date-channel.md, attachments are under new_paths.attach_dir
            # Relative from md_dir to attachment is: ../../attachments/<channel>/file
            rel_href = Path("..") / ".." / "attachments" / new_paths.channel / dest.name
            link_map[rel_path] = str(rel_href)
        except Exception:
            continue

    # Second pass: transform content
    lines = org_text.splitlines()
    out_lines: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Handle properties drawer (collect useful fields)
        if line.strip() == ":PROPERTIES:":
            props: Dict[str, str] = {}
            i += 1
            while i < len(lines) and lines[i].strip() != ":END:":
                pl = lines[i].strip()
                if pl.startswith(":") and ":" in pl[1:]:
                    try:
                        key, val = pl[1:].split(":", 1)
                        props[key.strip().upper()] = val.strip()
                    except Exception:
                        pass
                i += 1
            # skip the :END: line
            # Attach a permalink line if present
            if props.get("SLACK_LINK"):
                out_lines.append(f"Permalink: {props['SLACK_LINK']}")
            i += 1
            continue

        # Headings: * -> ##, ** -> ###, etc.
        mh = ORG_HEADER_RE.match(line)
        if mh:
            stars, text = mh.group(1), mh.group(2)
            level = len(stars) + 1  # file header will be #, messages start at ##
            out_lines.append("#" * level + " " + text)
            i += 1
            continue

        # Quotes: strip org quote markers
        if line.strip().lower() == "#+begin_quote":
            i += 1
            # copy until end_quote as plain text
            while i < len(lines) and lines[i].strip().lower() != "#+end_quote":
                out_lines.append(lines[i])
                i += 1
            i += 1  # skip end_quote
            continue

        # Replace file links inline
        def _link_sub(match: re.Match[str]) -> str:
            rel, title = match.group(1), match.group(2)
            href = link_map.get(rel, rel)
            return f"[{title}]({href})"

        line = ORG_LINK_RE.sub(_link_sub, line)
        out_lines.append(line)
        i += 1

    body = "\n".join(out_lines).strip() + "\n"
    return body, copied


def migrate_contextual_slack(old_root: str, entity: str, cfg: Optional[Config] = None) -> int:
    cfg = cfg or Config()
    old_root_path = Path(old_root).expanduser().resolve()
    if not old_root_path.exists():
        raise FileNotFoundError(old_root)

    org_dir, raw_dir, attach_dir = find_old_paths(old_root_path)

    # Iterate org files
    count = 0
    for org_path in sorted(org_dir.glob("*.org")):
        try:
            date_str, channel_name = parse_filename(org_path)
        except Exception:
            continue

        # Prepare new archive paths
        sap = SlackArchivePaths(_base_dir(cfg:=cfg), entity, channel_name)  # type: ignore[name-defined]

        # Skip if md already exists (idempotent)
        new_md = sap.md_path_for(date_str)
        if new_md.exists():
            continue

        # Convert and copy
        org_text = org_path.read_text(encoding="utf-8", errors="ignore")
        md_body, copied_files = convert_org_to_markdown(org_text, org_dir, raw_dir, sap, date_str)

        # Write markdown with header
        header = [f"# Slack Channel: {channel_name}", f"Date: {date_str}"]
        from mailflow.slack.storage import write_markdown

        write_markdown(new_md, header, md_body)

        # Copy JSON if available
        old_json = raw_dir / f"{date_str}-{channel_name}.json"
        if old_json.exists():
            from mailflow.slack.storage import write_json
            try:
                import json

                data = json.loads(old_json.read_text(encoding="utf-8"))
                write_json(sap.json_path_for(date_str), data)
            except Exception:
                pass

        # Optional: index
        llm_cfg = cfg.settings.get("llmemory", {})
        if llm_cfg.get("enabled"):
            base_root = validate_path(_base_dir(cfg))
            from mailflow.slack.ingest import index_memory_if_enabled

            rel_md = new_md.relative_to(base_root)
            index_memory_if_enabled(
                cfg,
                base_root,
                rel_md,
                md_body,
                {"channel": channel_name, "date": date_str, "workspace": "contextual-import"},
            )
            for f in copied_files:
                text = best_effort_text(f)
                if not text:
                    continue
                rel = f.relative_to(base_root)
                index_memory_if_enabled(
                    cfg,
                    base_root,
                    rel,
                    text,
                    {"channel": channel_name, "date": date_str, "workspace": "contextual-import"},
                )

        count += 1
    return count


