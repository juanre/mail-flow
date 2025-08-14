from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from pmail.config import Config
from pmail.security import validate_path
from pmail.slack.client import SlackClient, SlackConfig
from pmail.slack.markdown import render_transcript_md
from pmail.slack.storage import (
    SlackArchivePaths,
    compute_latest_ts,
    write_json,
    write_markdown,
)
from pmail.text_extract import best_effort_text


def _get_slack_settings(cfg: Config) -> Dict:
    return cfg.settings.get("slack", {})


def token_path_for_entity(cfg: Config, entity: str) -> Path:
    s = _get_slack_settings(cfg)
    # 1) explicit token_path in config
    ent = s.get("entities", {}).get(entity)
    if ent and ent.get("token_path"):
        return Path(ent["token_path"]).expanduser().resolve()
    # 2) XDG default: ~/.config/pmail/slack/<entity>/user_token
    import os

    xdg = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    xdg_path = (xdg / "pmail" / "slack" / entity / "user_token").resolve()
    if xdg_path.exists():
        return xdg_path
    # 3) Legacy fallback: ~/.pmail/slack/<entity>/user_token
    legacy = (cfg.config_dir / "slack" / entity / "user_token").resolve()
    return legacy


def _base_dir(cfg: Config) -> str:
    s = _get_slack_settings(cfg)
    return s.get("base_dir", "~/Documents/pmail/slack")


def _rate_limit(cfg: Config) -> float:
    s = _get_slack_settings(cfg)
    return float(s.get("rate_limit_min_interval_secs", 1.0))


def _ignored(cfg: Config) -> set[str]:
    s = _get_slack_settings(cfg)
    return {x.strip() for x in s.get("ignore_channels", [])}


def compute_oldest(paths: SlackArchivePaths, since_ts: Optional[float], force_full: bool) -> Optional[str]:
    if force_full:
        return None
    latest = compute_latest_ts(paths.raw_dir.glob(f"*-{paths.channel}.json"))
    if since_ts:
        latest = max(latest, since_ts)
    if latest > 0:
        return f"{latest + 0.000001:.6f}"
    return None


def group_messages_by_date(messages: Iterable[Dict]) -> Dict[str, List[Dict]]:
    buckets: Dict[str, List[Dict]] = defaultdict(list)
    for m in messages:
        date = datetime.fromtimestamp(float(m.get("ts", 0))).strftime("%Y-%m-%d")
        buckets[date].append(m)
    # sort each bucket by ts
    for v in buckets.values():
        v.sort(key=lambda x: float(x.get("ts", 0)))
        for p in v:
            if p.get("replies"):
                p["replies"].sort(key=lambda x: float(x.get("ts", 0)))
    return buckets


def _local_href(root: Path, target: Path) -> str:
    try:
        return str(target.relative_to(root))
    except Exception:
        return target.name


def _attachment_ext(file_obj: Dict) -> str:
    name = (file_obj.get("name") or "").lower()
    if "." in name:
        return "." + name.split(".")[-1]
    mime = (file_obj.get("mimetype") or file_obj.get("filetype") or "").lower()
    # very rough mapping
    if "pdf" in mime:
        return ".pdf"
    if "markdown" in mime or "md" == mime:
        return ".md"
    if "text" in mime:
        return ".txt"
    return ""


def download_attachments(client: SlackClient, paths: SlackArchivePaths, channel_name: str, messages: List[Dict]) -> None:
    for m in messages:
        files = m.get("files") or []
        for f in files:
            url = f.get("url_private_download") or f.get("url_private")
            if not url:
                continue
            ts = datetime.fromtimestamp(float(f.get("timestamp") or m.get("ts") or 0))
            title = f.get("title") or f.get("name") or "file"
            ext = _attachment_ext(f)
            dest = paths.attachment_path(ts, title, ext)
            client.download_private_url(url, dest)
            # Inject local href for markdown rendering
            f["_local_href"] = _local_href(paths.md_dir.parent, dest)


def index_memory_if_enabled(cfg: Config, base_root: Path, rel_path: Path, content: str, metadata: Dict) -> None:
    llm_cfg = cfg.settings.get("llmemory", {})
    if not llm_cfg.get("enabled"):
        return
    try:
        from llmemory import AwordMemory, DocumentType
        import asyncio

        async def _run():
            memory = AwordMemory(
                connection_string=llm_cfg.get("connection_string"),
                openai_api_key=llm_cfg.get("openai_api_key"),
            )
            await memory.initialize()
            try:
                await memory.add_document(
                    owner_id=llm_cfg.get("owner_id", "default-owner"),
                    id_at_origin=str(rel_path),
                    document_name=rel_path.name,
                    document_type=DocumentType.CHAT if rel_path.suffix == ".md" else DocumentType.TEXT,
                    content=content,
                    metadata={**metadata, "relative_path": str(rel_path)},
                )
            finally:
                await memory.close()

        asyncio.run(_run())
    except Exception:
        # best-effort; do not fail ingestion
        pass


def ingest_channel(
    cfg: Config,
    entity: str,
    channel_id: str,
    channel_name: str,
    since_ts: Optional[float] = None,
    force_full: bool = False,
) -> int:
    token_path = token_path_for_entity(cfg, entity)
    client = SlackClient(
        SlackConfig(token_path=token_path, rate_limit_min_interval_secs=_rate_limit(cfg))
    )
    workspace = client.team_domain()
    users = client.users_map()

    base_dir = _base_dir(cfg)
    import os
    base_root = validate_path(base_dir, allowed_base_dirs=[os.path.expanduser("~"), base_dir])
    paths = SlackArchivePaths(base_dir, entity, channel_name)
    oldest = compute_oldest(paths, since_ts, force_full)

    # gather messages and attach replies
    messages: List[Dict] = []
    for m in client.history(channel_id, oldest=oldest):
        messages.append(m)
        if m.get("thread_ts") and m.get("thread_ts") == m.get("ts"):
            try:
                reps = client.replies(channel_id, m["ts"])  # type: ignore
                if reps:
                    m["replies"] = reps
            except Exception:
                pass

    if not messages:
        return 0

    # download attachments first so we can link them in markdown
    download_attachments(client, paths, channel_name, messages)

    # group per day and write
    by_date = group_messages_by_date(messages)
    total = 0
    for date_str, msgs in by_date.items():
        md_path = paths.md_path_for(date_str)
        json_path = paths.json_path_for(date_str)

        # write JSON
        write_json(json_path, msgs)

        # write MD (render after we inject local hrefs)
        md_content = render_transcript_md(channel_name, date_str, workspace, users, msgs)
        write_markdown(md_path, [], md_content)  # content already includes header

        # index transcript
        rel_md = md_path.relative_to(base_root)
        index_memory_if_enabled(
            cfg,
            base_root,
            rel_md,
            content=md_content,
            metadata={"channel": channel_name, "workspace": workspace, "date": date_str},
        )

        # index attachments
        for m in msgs:
            for f in m.get("files") or []:
                href = f.get("_local_href")
                if not href:
                    continue
                attach_path = base_root / href
                text = best_effort_text(attach_path)
                if not text:
                    continue
                rel_att = attach_path.relative_to(base_root)
                index_memory_if_enabled(
                    cfg,
                    base_root,
                    rel_att,
                    content=text,
                    metadata={
                        "channel": channel_name,
                        "workspace": workspace,
                        "date": date_str,
                        "slack_file_id": f.get("id"),
                        "permalink": f.get("permalink"),
                    },
                )

        total += len(msgs)
    return total


