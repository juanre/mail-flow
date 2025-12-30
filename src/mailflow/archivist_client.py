"""Async client for the llm-archivist Classifier.

Exposes async API for proper connection pool management. All functions
are async and should be awaited within a single event loop at the CLI level."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from llm_archivist import Classifier as ArchivistClassifier
from llm_archivist import ClassifyOpts, Decision, Workflow

_classifier: Optional[ArchivistClassifier] = None


def _use_db_mode() -> bool:
    """Return True when archivist should run in DB mode."""
    use_db = os.getenv("ARCHIVIST_USE_DB", "0").strip().lower() in {"1", "true", "yes", "on"}
    db_url = os.getenv("DATABASE_URL")
    return bool(use_db and db_url)


async def _get_classifier() -> ArchivistClassifier:
    """Get or create the classifier (async initialization for DB mode)."""
    global _classifier
    if _classifier is None:
        if _use_db_mode():
            _classifier = await ArchivistClassifier.from_env_async()
        else:
            _classifier = ArchivistClassifier.from_env()
    return _classifier


async def classify(
    text: str,
    meta: Dict[str, Any],
    workflows: List[Workflow],
    opts: Optional[ClassifyOpts] = None,
) -> Decision:
    """Classify using archivist. Must be awaited within an event loop."""
    clf = await _get_classifier()
    if _use_db_mode():
        return await clf.classify_async(text, meta, workflows, opts=opts)
    return clf.classify(text, meta, workflows, opts=opts)


async def feedback(decision_id: int, label: str, reason: str | None = None) -> None:
    """Record feedback for a prior decision. Must be awaited."""
    clf = await _get_classifier()
    if _use_db_mode():
        await clf.feedback_async(int(decision_id), label, reason)
    else:
        clf.feedback(int(decision_id), label, reason)


async def get_metrics() -> Dict[str, Any]:
    """Return basic metrics from archivist. Must be awaited."""
    clf = await _get_classifier()
    if _use_db_mode():
        return await clf.get_metrics_async()
    return clf.get_metrics()
