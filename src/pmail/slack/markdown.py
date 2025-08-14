from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List


def replace_mentions(text: str, users: Dict[str, str]) -> str:
    def repl(m: re.Match[str]) -> str:
        uid = m.group(1)
        return f"@{users.get(uid, uid)}"

    return re.sub(r"<@([A-Z0-9]+)>", repl, text or "")


def permalink(workspace: str, channel: str, ts: str) -> str:
    return f"https://{workspace}.slack.com/archives/{channel}/p{ts.replace('.', '')}"


def format_message_md(
    message: Dict,
    users: Dict[str, str],
    workspace: str,
    channel_name: str,
    indent_level: int = 0,
) -> str:
    ts = float(message.get("ts", "0"))
    dt = datetime.fromtimestamp(ts)
    user = users.get(message.get("user", ""), "Unknown User")
    header = f"{'#' * (indent_level + 2)} {user} — {dt.isoformat()}\n"
    link = permalink(workspace, channel_name, message.get("ts", "0"))
    header += f"Permalink: {link}\n\n"
    body = replace_mentions(message.get("text", ""), users)
    out = header + (body + "\n\n" if body.strip() else "")

    # attachments (links only; rendering of extracted content left to file view)
    files = message.get("files") or []
    if files:
        out += f"{'#' * (indent_level + 3)} Attachments\n"
        for f in files:
            title = f.get("title") or f.get("name") or "file"
            # actual href to be provided by caller that knows local path
            href = f.get("_local_href")  # injected by ingest
            if href:
                out += f"- [{title}]({href})\n"
        out += "\n"

    # replies
    for rep in message.get("replies", []) or []:
        out += format_message_md(rep, users, workspace, channel_name, indent_level + 1)
    return out


def render_transcript_md(
    channel_name: str,
    date_str: str,
    workspace: str,
    users: Dict[str, str],
    messages: List[Dict],
) -> str:
    lines: List[str] = [f"# Slack Channel: {channel_name}", f"Date: {date_str}"]
    body_parts: List[str] = []
    for m in messages:
        body_parts.append(format_message_md(m, users, workspace, channel_name, 0))
    return "\n\n".join(["\n".join(lines), "".join(body_parts)])


