"""Integration helpers to use llm-archivist for workflow classification.

Builds inputs (text + metadata) and maps results into mailflow structures.
All classification functions are async for proper connection pool management."""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from llm_archivist import Workflow

logger = logging.getLogger(__name__)

from mailflow.archivist_client import classify as archivist_classify
from mailflow.archivist_client import feedback as archivist_feedback


def _build_text(email_data: dict) -> str:
    """Build classifier text from email fields.

    Raises:
        ValueError: If from or to address is missing.
    """
    subject = (email_data.get("subject") or "").strip()
    body = email_data.get("body") or ""  # Full body, no truncation
    from_addr = (email_data.get("from") or "").strip()
    to_addr = (email_data.get("to") or "").strip()

    if not from_addr or not to_addr:
        raise ValueError("Email missing required from/to address")

    # Get PDF attachment names
    attachments = email_data.get("attachments") or []
    pdf_names = [a["filename"] for a in attachments if a.get("is_pdf") and a.get("filename")]

    header_lines = [
        "Source: email",
        f"From: {from_addr}",
        f"To: {to_addr}",
        f"Subject: {subject}" if subject else "",
        f"PDF attachments: {', '.join(pdf_names)}" if pdf_names else "",
    ]
    header = "\n".join([h for h in header_lines if h])

    if body:
        return f"{header}\n\n{body}".strip()
    return header.strip()


def _render_email_pdf_to_file_sync(email_data: dict) -> str | None:
    """Sync implementation of PDF rendering. Runs in thread pool."""
    message_obj = email_data.get("_message_obj")
    if not message_obj:
        return None

    try:
        from mailflow.pdf_converter import email_to_pdf_bytes, extract_best_html_from_message

        _, is_html = extract_best_html_from_message(message_obj)
        if not is_html:
            return None

        pdf_bytes = email_to_pdf_bytes(message_obj, email_data)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            return tmp.name
    except Exception as e:
        logger.warning(f"PDF rendering failed, falling back to text-only: {e}")
        return None


def _extract_pdf_attachment_to_file_sync(email_data: dict) -> str | None:
    """Extract the best PDF attachment (by size) into a temp file. Returns path or None.

    This provides the LLM with the actual invoice/receipt PDF when present, which is
    typically far more informative than a rendered HTML email.
    """
    message_obj = email_data.get("_message_obj")
    if not message_obj:
        return None

    try:
        from mailflow.attachment_handler import extract_attachments

        pdf_attachments = extract_attachments(message_obj, pattern="*.pdf")
        if not pdf_attachments:
            return None

        # Prefer the largest PDF (often the primary invoice/receipt).
        filename, content, mimetype = max(pdf_attachments, key=lambda a: len(a[1] or b""))
        if not content:
            return None
        if mimetype not in ("application/pdf", "application/octet-stream"):
            # Still allow application/octet-stream because many mailers label PDFs loosely.
            pass

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            return tmp.name
    except Exception as e:
        logger.warning(f"PDF attachment extraction failed, falling back: {e}")
        return None


async def _extract_pdf_attachment_to_file(email_data: dict) -> str | None:
    """Async wrapper around PDF attachment extraction (thread pool)."""
    import asyncio

    return await asyncio.to_thread(_extract_pdf_attachment_to_file_sync, email_data)


async def _render_email_pdf_to_file(email_data: dict) -> str | None:
    """Render email to PDF temp file if body is HTML. Returns path or None.

    Runs sync Playwright in a thread pool to avoid blocking the event loop.
    Caller is responsible for cleanup. Falls back to None on failure.
    """
    import asyncio

    return await asyncio.to_thread(_render_email_pdf_to_file_sync, email_data)


def _build_meta(email_data: dict) -> dict:
    """Build structured metadata for archivist."""
    atts = email_data.get("attachments") or []
    return {
        "source": "email",
        "from": email_data.get("from"),
        "to": email_data.get("to"),
        "date": email_data.get("date"),
        "message_id": email_data.get("message_id"),
        "attachments": [a.get("filename") for a in atts if a.get("filename")],
        "has_attachments": bool(atts),
        "has_pdf": any(a.get("is_pdf") for a in atts),
    }


def _build_workflows(data_store) -> List[Workflow]:
    """Convert mailflow workflows into archivist workflow definitions."""
    workflows: List[Workflow] = []
    for name, wf in (data_store.workflows or {}).items():
        workflows.append(
            {
                "name": name,
                "description": getattr(wf, "description", name) or name,
                "tags": [],
            }
        )
    return workflows


async def classify_with_archivist(
    email_data: dict,
    data_store,
    *,
    interactive: bool = True,
    allow_llm: bool = True,
    max_candidates: int = 5,
    classifier: Optional[Any] = None,
    workflow_filter: Optional[List[str]] = None,
) -> dict:
    """
    Run llm-archivist classification and return a mailflow-compatible result.

    This is an async function that must be awaited. Returns a dict with keys:
    label, confidence, rankings, evidence, advisors_used.

    Args:
        workflow_filter: If provided, only classify against these workflow names.
    """
    text = _build_text(email_data)
    meta = _build_meta(email_data)
    workflows = _build_workflows(data_store)

    # Filter workflows if specified
    if workflow_filter:
        workflows = [w for w in workflows if w["name"] in workflow_filter]
    if not workflows:
        return {"label": None, "confidence": 0.0, "candidates": []}

    opts: Dict[str, Any] = {
        "allow_llm": bool(allow_llm),
        "interactive": bool(interactive),
        "max_candidates": int(max_candidates),
    }

    # Provide the LLM with a PDF if available:
    # 1) Prefer an actual PDF attachment (often the real invoice/receipt).
    # 2) Otherwise, render the HTML email body to PDF.
    pdf_path = await _extract_pdf_attachment_to_file(email_data)
    if not pdf_path:
        pdf_path = await _render_email_pdf_to_file(email_data)

    try:
        # Allow tests to inject a fake classifier; otherwise use shared archivist client.
        if classifier is not None:
            # Test classifiers may be sync or async
            if hasattr(classifier, "classify_async"):
                decision = await classifier.classify_async(
                    text, meta, workflows, opts=opts, pdf_path=pdf_path
                )
            else:
                decision = classifier.classify(text, meta, workflows, opts=opts, pdf_path=pdf_path)
        else:
            decision = await archivist_classify(text, meta, workflows, opts=opts, pdf_path=pdf_path)
    except Exception as e:
        logger.warning(f"Classification failed: {e}")
        return {"label": None, "confidence": 0.0, "candidates": []}
    finally:
        # Cleanup temp PDF file
        if pdf_path:
            try:
                os.unlink(pdf_path)
            except FileNotFoundError:
                pass  # Already cleaned up
            except Exception as e:
                logger.debug(f"Failed to cleanup temp PDF {pdf_path}: {e}")

    candidates = decision.get("candidates") or []
    rankings: List[Tuple[str, float, list]] = [
        (c.get("label"), float(c.get("confidence", 0.0)), []) for c in candidates if c.get("label")
    ]
    return {
        "decision_id": decision.get("decision_id"),
        "label": decision.get("label"),
        "confidence": float(decision.get("confidence", 0.0)),
        "rankings": rankings,
        "evidence": decision.get("evidence", {}),
        "advisors_used": decision.get("advisors_used", []),
    }


async def record_feedback(decision_id: int, label: str, reason: str | None = None) -> None:
    """Send feedback to llm-archivist. Must be awaited."""
    try:
        await archivist_feedback(int(decision_id), str(label), reason)
    except Exception as e:
        logger.warning(f"Failed to record feedback for decision {decision_id}: {e}")
