"""Synchronous wrapper around the llm-archivist Classifier.

Provides a simple sync API for mailflow while supporting DB/async mode."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

from llm_archivist import Classifier as ArchivistClassifier
from llm_archivist import ClassifyOpts, Decision, Workflow

_sync_classifier: Optional[ArchivistClassifier] = None
_async_classifier: Optional[ArchivistClassifier] = None


def _use_db_mode() -> bool:
    """Return True when archivist should run in DB mode."""
    use_db = os.getenv("ARCHIVIST_USE_DB", "0").strip().lower() in {"1", "true", "yes", "on"}
    db_url = os.getenv("DATABASE_URL")
    return bool(use_db and db_url)


def _get_sync_classifier() -> ArchivistClassifier:
    """Get or create a synchronous classifier (dev mode only)."""
    global _sync_classifier
    if _sync_classifier is None:
        _sync_classifier = ArchivistClassifier.from_env()
    return _sync_classifier


async def _get_async_classifier() -> ArchivistClassifier:
    """Get or create an async classifier (DB or dev mode)."""
    global _async_classifier
    if _async_classifier is None:
        _async_classifier = await ArchivistClassifier.from_env_async()
    return _async_classifier


def _run_coro(coro):
    """Run an async coroutine from sync code."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        return loop.run_until_complete(coro)


def classify(
    text: str,
    meta: Dict[str, Any],
    workflows: List[Workflow],
    opts: Optional[ClassifyOpts] = None,
) -> Decision:
    """Classify using archivist, handling DB/async transparently."""
    if _use_db_mode() and hasattr(ArchivistClassifier, "from_env_async"):
        async def _run() -> Decision:
            clf = await _get_async_classifier()
            return await clf.classify_async(text, meta, workflows, opts=opts)

        return _run_coro(_run())

    clf = _get_sync_classifier()
    return clf.classify(text, meta, workflows, opts=opts)


def feedback(decision_id: int, label: str, reason: str | None = None) -> None:
    """Record feedback for a prior decision."""
    if _use_db_mode() and hasattr(ArchivistClassifier, "from_env_async"):
        async def _run() -> None:
            clf = await _get_async_classifier()
            await clf.feedback_async(int(decision_id), label, reason)

        _run_coro(_run())
        return

    clf = _get_sync_classifier()
    clf.feedback(int(decision_id), label, reason)


def get_metrics() -> Dict[str, Any]:
    """Return basic metrics from archivist."""
    if _use_db_mode() and hasattr(ArchivistClassifier, "from_env_async"):
        async def _run() -> Dict[str, Any]:
            clf = await _get_async_classifier()
            return await clf.get_metrics_async()

        return _run_coro(_run())

    clf = _get_sync_classifier()
    return clf.get_metrics()
