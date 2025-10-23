from __future__ import annotations

import json
import os
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
]


@dataclass
class GoogleCredPaths:
    client_secret: Optional[Path]
    token_json: Optional[Path]
    token_pickle: Optional[Path]


def _find_google_cred_paths() -> GoogleCredPaths:
    # XDG
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    xdg_dir = (xdg / "mailflow" / "google").resolve()
    client_secret = xdg_dir / "client_secret.json"
    token_json = xdg_dir / "token.json"
    # contextual legacy token path if copied via setup
    token_pickle = (xdg / "mailflow" / "auth").resolve()
    # find any token.pickle under auth/*/google/
    tp: Optional[Path] = None
    if token_pickle.exists():
        for p in token_pickle.rglob("token.pickle"):
            tp = p
            break

    # legacy ~/.mailflow
    legacy_dir = Path("~/.mailflow").expanduser()
    if not client_secret.exists():
        alt = legacy_dir / "gmail_client_secret.json"
        client_secret = alt if alt.exists() else None  # type: ignore
    if not token_json.exists():
        alt = legacy_dir / "gmail_token.json"
        token_json = alt if alt.exists() else None  # type: ignore

    return GoogleCredPaths(
        client_secret=client_secret if isinstance(client_secret, Path) and client_secret.exists() else None,
        token_json=token_json if isinstance(token_json, Path) and token_json.exists() else None,
        token_pickle=tp if isinstance(tp, Path) and tp.exists() else None,
    )


def _load_credentials(paths: GoogleCredPaths) -> Credentials:
    creds: Optional[Credentials] = None
    # Try token.json first
    if paths.token_json and paths.token_json.exists():
        try:
            data = json.loads(paths.token_json.read_text())
            creds = Credentials.from_authorized_user_info(data, scopes=SCOPES)
        except Exception:
            creds = None
    # Try token.pickle (contextual legacy)
    if creds is None and paths.token_pickle and paths.token_pickle.exists():
        try:
            with open(paths.token_pickle, "rb") as f:
                creds = pickle.load(f)
        except Exception:
            creds = None

    if creds is None:
        raise RuntimeError(
            "No Google credentials found. Place token.json at ~/.config/mailflow/google/ or run mailflow setup."
        )

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            pass
    return creds


class GoogleClient:
    def __init__(self):
        paths = _find_google_cred_paths()
        self._creds = _load_credentials(paths)
        self._drive = build("drive", "v3", credentials=self._creds, cache_discovery=False)
        self._docs = build("docs", "v1", credentials=self._creds, cache_discovery=False)

    @property
    def drive(self):
        return self._drive

    @property
    def docs(self):
        return self._docs

    def file_metadata(self, file_id: str) -> Dict[str, Any]:
        return (
            self._drive.files()
            .get(fileId=file_id, fields="id, name, mimeType, modifiedTime, createdTime, parents")
            .execute()
        )

    def export_markdown(self, file_id: str) -> bytes:
        # Google Docs markdown export
        req = self._drive.files().export(fileId=file_id, mimeType="text/markdown")
        return req.execute()

    def export_pdf(self, file_id: str) -> bytes:
        req = self._drive.files().export(fileId=file_id, mimeType="application/pdf")
        return req.execute()

    def download_binary(self, file_id: str) -> bytes:
        req = self._drive.files().get_media(fileId=file_id)
        # MediaIoBaseDownload is chunked; but for small files .execute() on export-like doesn't apply.
        # Use .get_media with .to_json() isn't correct; fallback to simple request via http client.
        # Use internal http to download content.
        from googleapiclient.http import HttpRequest

        http = self._drive._http  # type: ignore[attr-defined]
        request: HttpRequest = req
        _, content = request.next_chunk(http=http)  # type: ignore[arg-type]
        return content or b""


