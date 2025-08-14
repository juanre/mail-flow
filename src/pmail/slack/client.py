from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


@dataclass
class SlackConfig:
    token_path: Path
    rate_limit_min_interval_secs: float = 1.0


class SlackClient:
    """Thin wrapper over slack_sdk.WebClient with token loading and throttling."""

    def __init__(self, config: SlackConfig):
        token = (config.token_path.expanduser()).read_text(encoding="utf-8").strip()
        if not token:
            raise RuntimeError(f"Empty Slack token at {config.token_path}")
        self._client = WebClient(token=token)
        self._token = token
        self._min_interval = max(0.0, config.rate_limit_min_interval_secs)
        self._last_call = 0.0

    def _throttle(self) -> None:
        now = time.time()
        delta = now - self._last_call
        if delta < self._min_interval:
            time.sleep(self._min_interval - delta)
        self._last_call = time.time()

    def _call(self, fn, *args, **kwargs):
        retries = 5
        backoff = 1.0
        while True:
            self._throttle()
            try:
                return fn(*args, **kwargs)
            except SlackApiError as e:
                err = e.response.get("error") if hasattr(e, "response") else str(e)
                if hasattr(e, "response") and e.response.status_code == 429:
                    retry_after = int(e.response.headers.get("Retry-After", "1"))
                    time.sleep(retry_after)
                    continue
                retries -= 1
                if retries <= 0:
                    raise
                time.sleep(backoff)
                backoff *= 2

    def team_domain(self) -> str:
        res = self._call(self._client.team_info)
        return res["team"]["domain"]

    def users_map(self) -> Dict[str, str]:
        users: Dict[str, str] = {}
        res = self._call(self._client.users_list)
        for u in res.get("members", []):
            display = u.get("profile", {}).get("display_name") or u.get("profile", {}).get(
                "real_name"
            )
            if u.get("id") and display:
                users[u["id"]] = display
        return users

    def list_conversations(self, include_archived: bool) -> List[Tuple[str, str, Dict[str, Any]]]:
        types = "public_channel,private_channel,im,mpim"
        cursor: Optional[str] = None
        results: List[Tuple[str, str, Dict[str, Any]]] = []
        while True:
            res = self._call(
                self._client.conversations_list,
                types=types,
                cursor=cursor,
                exclude_archived=not include_archived,
                limit=200,
            )
            for ch in res.get("channels", []):
                name = ch.get("name")
                if ch.get("is_im") and ch.get("user"):
                    # best-effort DM name
                    try:
                        info = self._call(self._client.users_info, user=ch["user"])
                        name = f"dm-{info['user']['name']}"
                    except Exception:
                        name = f"dm-{ch['id']}"
                elif ch.get("is_mpim"):
                    name = f"mpdm-{ch['id']}"
                if name:
                    results.append((ch["id"], name, ch))
            cursor = res.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        return results

    def find_channel(self, channel_name_or_id: str) -> Tuple[str, str]:
        if channel_name_or_id.startswith("C"):
            try:
                ch = self._call(self._client.conversations_info, channel=channel_name_or_id)[
                    "channel"
                ]
                if ch.get("is_im") and ch.get("user"):
                    info = self._call(self._client.users_info, user=ch["user"])  # type: ignore
                    return ch["id"], f"dm-{info['user']['name']}"
                return ch["id"], ch.get("name", ch["id"])  # type: ignore
            except SlackApiError:
                pass
        for cid, name, _meta in self.list_conversations(include_archived=True):
            if name == channel_name_or_id or name.lower() == channel_name_or_id.lower():
                return cid, name
        raise RuntimeError(f"Channel not found: {channel_name_or_id}")

    def history(self, channel_id: str, oldest: Optional[str] = None) -> Iterable[Dict[str, Any]]:
        cursor: Optional[str] = None
        while True:
            res = self._call(
                self._client.conversations_history,
                channel=channel_id,
                cursor=cursor,
                oldest=oldest,
                limit=200,
                inclusive=True,
            )
            for m in res.get("messages", []):
                yield m
            cursor = res.get("response_metadata", {}).get("next_cursor")
            if not cursor or not res.get("has_more", False):
                break

    def replies(self, channel_id: str, thread_ts: str) -> List[Dict[str, Any]]:
        res = self._call(self._client.conversations_replies, channel=channel_id, ts=thread_ts)
        return res.get("messages", [])[1:]  # skip parent

    def download_private_url(self, url: str, dest: Path) -> None:
        headers = {"Authorization": f"Bearer {self._token}"}
        with requests.get(url, headers=headers, stream=True) as r:
            r.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)


