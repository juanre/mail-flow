import json
import re
from pathlib import Path
from typing import Optional

from mailflow.global_index import GlobalIndex


def _extract_date_from_name(name: str) -> str:
    m = re.match(r"(\d{4}-\d{2}-\d{2})-", name)
    return m.group(1) if m else "1970-01-01"


def run_indexer(base_path: str, indexes_path: Optional[str] = None) -> int:
    """Scan archive at base_path and populate global indexes.

    Returns number of documents indexed (not streams).
    """
    base = Path(base_path).expanduser().resolve()
    if indexes_path is None:
        indexes_path = str(base / "indexes")
    gi = GlobalIndex(indexes_path)

    count = 0

    # Iterate entities (directories in base)
    for entity_dir in [p for p in base.iterdir() if p.is_dir() and p.name not in {"indexes", "tmp"}]:
        entity = entity_dir.name

        # Docs
        docs_dir = entity_dir / "docs"
        if docs_dir.exists():
            for year_dir in docs_dir.iterdir():
                if not year_dir.is_dir():
                    continue
                for doc_path in year_dir.glob("*.*"):
                    if not doc_path.is_file():
                        continue
                    ext = doc_path.suffix.lower()
                    if ext not in {".pdf", ".csv"}:
                        continue
                    # Expect metadata JSON sibling
                    meta_path = doc_path.with_suffix(".json")
                    origin = {}
                    workflow = None
                    category = None
                    confidence = None
                    source = "email"
                    if meta_path.exists():
                        try:
                            md = json.loads(meta_path.read_text())
                            origin = md.get("origin", {})
                            workflow = md.get("workflow")
                            clf = origin.get("classifier") or {}
                            category = clf.get("category")
                            confidence = clf.get("confidence")
                            source = md.get("source", source)
                        except Exception:
                            origin = {}
                    rel = str(doc_path.relative_to(entity_dir))
                    data = {
                        "entity": entity,
                        "date": _extract_date_from_name(doc_path.name),
                        "filename": doc_path.name,
                        "rel_path": rel,
                        "hash": None,
                        "size": doc_path.stat().st_size,
                        "type": ext.lstrip("."),
                        "source": source,
                        "workflow": workflow,
                        "category": category,
                        "confidence": confidence,
                        "origin_json": json.dumps(origin),
                        "structured_json": None,
                    }
                    doc_id = gi.upsert_document(data)

                    # Build FTS content
                    email_subject = str(origin.get("subject", ""))
                    email_from = str(origin.get("from", ""))
                    search_content = " ".join(
                        [email_subject, email_from, doc_path.stem.replace("-", " ")]
                    )
                    gi.upsert_fts(doc_id, doc_path.name, email_subject, email_from, search_content)
                    count += 1

        # Streams
        streams_dir = entity_dir / "streams"
        if streams_dir.exists():
            # Slack streams: streams/slack/{channel}/{YYYY}/files
            slack_dir = streams_dir / "slack"
            if slack_dir.exists():
                for channel_dir in [p for p in slack_dir.iterdir() if p.is_dir()]:
                    channel = channel_dir.name
                    for year_dir in [p for p in channel_dir.iterdir() if p.is_dir()]:
                        for md_path in year_dir.glob("*.md"):
                            rel = str(md_path.relative_to(entity_dir))
                            sid = gi.upsert_stream(
                                {
                                    "entity": entity,
                                    "kind": "slack",
                                    "channel_or_mailbox": channel,
                                    "date": _extract_date_from_name(md_path.name),
                                    "rel_path": rel,
                                    "origin_json": json.dumps({}),
                                }
                            )
                            # Link docs referenced in transcript
                            try:
                                text = md_path.read_text()
                                for match in re.findall(r"\((\.\./)+docs/\d{4}/[^)]+\)", text):
                                    # normalize rel path from entity_dir
                                    # remove leading ../../..
                                    link = match.strip("()")
                                    parts = link.split("docs/")
                                    if len(parts) == 2:
                                        rel_doc = "docs/" + parts[1]
                                        row = None
                                        with gi._conn() as conn:
                                            row = conn.execute(
                                                "SELECT id FROM documents WHERE entity=? AND rel_path=?",
                                                (entity, rel_doc),
                                            ).fetchone()
                                        if row:
                                            gi.add_link(sid, int(row[0]))
                            except Exception:
                                pass

    return count

