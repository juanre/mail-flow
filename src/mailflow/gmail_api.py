# ABOUTME: Gmail API integration for fetching and processing emails via OAuth2
# ABOUTME: Manages authentication, message retrieval, and label-based organization
"""Gmail API integration for fetching and processing emails without a local mailbox.

This module intentionally keeps imports to Gmail libraries inside functions so the
rest of the application works without the optional dependency installed.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from mailflow.config import Config
from mailflow.exceptions import EmailParsingError
from mailflow.process import process as process_email

logger = logging.getLogger(__name__)


GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]


@dataclass
class GmailPaths:
    client_secret_path: Path
    token_path: Path


def _get_paths(config: Config) -> GmailPaths:
    base = config.config_dir
    return GmailPaths(
        client_secret_path=base / "gmail_client_secret.json",
        token_path=base / "gmail_token.json",
    )


def _require_google_libs():
    try:
        from googleapiclient.discovery import build  # type: ignore
        from googleapiclient.errors import HttpError  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore
        from google.oauth2.credentials import Credentials  # type: ignore
        from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
    except Exception as e:  # pragma: no cover - import-time environment dependent
        raise RuntimeError(
            "Missing Gmail API dependencies. Install with:\n"
            "  uv add google-api-python-client google-auth google-auth-oauthlib"
        ) from e

    return build, HttpError, Request, Credentials, InstalledAppFlow


def get_gmail_service(config: Config):
    """Authenticate and return a Gmail API service client.

    Requires a client secrets JSON at ~/.config/mailflow/gmail_client_secret.json.
    """
    build, HttpError, Request, Credentials, InstalledAppFlow = _require_google_libs()

    paths = _get_paths(config)
    creds = None

    if paths.token_path.exists():
        creds = Credentials.from_authorized_user_file(str(paths.token_path), GMAIL_SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not paths.client_secret_path.exists():
                raise RuntimeError(
                    f"Gmail client secret not found at {paths.client_secret_path}.\n"
                    "Create an OAuth client (Desktop) in Google Cloud Console and place the JSON here."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(paths.client_secret_path), GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(paths.token_path, "w") as token:
            token.write(creds.to_json())

    service = build("gmail", "v1", credentials=creds)
    return service


def list_message_ids(
    service, query: str = "", label_ids: Optional[List[str]] = None, max_results: int = 50
) -> List[str]:
    """List message IDs matching the query/labels."""
    label_ids = label_ids or []
    response = (
        service.users()
        .messages()
        .list(userId="me", q=query, labelIds=label_ids, maxResults=max_results)
        .execute()
    )
    msgs = response.get("messages", [])
    return [m["id"] for m in msgs]


def get_message_raw(service, message_id: str) -> str:
    """Fetch a Gmail message as raw RFC822 text (decoded)."""
    resp = service.users().messages().get(userId="me", id=message_id, format="raw").execute()
    raw = resp.get("raw")
    if not raw:
        return ""
    # Gmail returns base64url-encoded raw RFC822 content
    return base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8", errors="replace")


def ensure_label(service, label_name: str) -> str:
    """Ensure a label exists, return its ID."""
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for l in labels:
        if l.get("name") == label_name:
            return l.get("id")
    created = (
        service.users()
        .labels()
        .create(userId="me", body={"name": label_name, "labelListVisibility": "labelShow"})
        .execute()
    )
    return created["id"]


def modify_labels(
    service, message_id: str, add_labels: Iterable[str] = (), remove_labels: Iterable[str] = ()
) -> None:
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"addLabelIds": list(add_labels), "removeLabelIds": list(remove_labels)},
    ).execute()


def poll_and_process(
    config: Config,
    query: str = "",
    label: Optional[str] = None,
    processed_label: str = "mailflow/processed",
    max_results: int = 20,
    remove_from_inbox: bool = False,
) -> int:
    """Fetch messages via Gmail API and process them with the existing pipeline.

    Returns the number of successfully processed messages.
    """
    service = get_gmail_service(config)

    label_ids = None
    if label:
        label_id = ensure_label(service, label)
        label_ids = [label_id]

    msg_ids = list_message_ids(service, query=query, label_ids=label_ids, max_results=max_results)
    if not msg_ids:
        logger.info("No messages matched Gmail query/labels.")
        return 0

    processed_label_id = ensure_label(service, processed_label) if processed_label else None
    inbox_label_id = None
    if remove_from_inbox:
        # Inbox label has fixed id 'INBOX' in API
        inbox_label_id = "INBOX"

    count = 0
    transient_errors = 0
    max_transient_errors = 3

    for mid in msg_ids:
        try:
            raw = get_message_raw(service, mid)
            if not raw:
                logger.warning(f"Message {mid} had no raw content; skipping")
                continue

            process_email(raw, config=config)

            # Label management
            add_ids = []
            remove_ids = []
            if processed_label_id:
                add_ids.append(processed_label_id)
            if remove_from_inbox and inbox_label_id:
                remove_ids.append(inbox_label_id)
            if add_ids or remove_ids:
                modify_labels(service, mid, add_labels=add_ids, remove_labels=remove_ids)

            # Only increment count and reset errors after all operations succeed
            count += 1
            transient_errors = 0

        except EmailParsingError as e:
            # Permanent error - log and skip
            logger.error(f"Invalid email format for message {mid}: {e}")
            continue

        except Exception as e:
            # Could be transient network error
            transient_errors += 1
            logger.exception(f"Failed to process Gmail message {mid}: {e}")

            if transient_errors >= max_transient_errors:
                logger.error(f"Too many consecutive errors ({transient_errors}), stopping")
                break

            # Exponential backoff
            backoff = 2**transient_errors
            logger.info(f"Retrying after {backoff}s backoff")
            time.sleep(backoff)
            continue

    return count
