"""Async client for the llm-archivist Classifier.

Always uses database mode for persistent learning. Requires DATABASE_URL to be set."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from llm_archivist import Classifier as ArchivistClassifier
from llm_archivist import ClassifyOpts, Decision, Workflow

_classifier: Optional[ArchivistClassifier] = None


async def _get_classifier() -> ArchivistClassifier:
    """Get or create the classifier with async DB initialization."""
    global _classifier
    if _classifier is None:
        if not os.getenv("DATABASE_URL"):
            raise RuntimeError(
                "DATABASE_URL not set. Required for persistent learning.\n"
                "Add to .env: DATABASE_URL='postgresql://user:pass@localhost:5432/dbname'"
            )
        _classifier = await ArchivistClassifier.from_env_async()
    return _classifier


async def classify(
    text: str,
    meta: Dict[str, Any],
    workflows: List[Workflow],
    opts: Optional[ClassifyOpts] = None,
) -> Decision:
    """Classify using archivist. Must be awaited within an event loop."""
    clf = await _get_classifier()
    return await clf.classify_async(text, meta, workflows, opts=opts)


async def feedback(decision_id: int, label: str, reason: str | None = None) -> None:
    """Record feedback for a prior decision. Must be awaited."""
    clf = await _get_classifier()
    await clf.feedback_async(int(decision_id), label, reason)


async def get_metrics() -> Dict[str, Any]:
    """Return basic metrics from archivist. Must be awaited."""
    clf = await _get_classifier()
    return await clf.get_metrics_async()
