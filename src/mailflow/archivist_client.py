"""Async client for the llm-archivist Classifier.

Always uses database mode for persistent learning.
Requires archivist.database_url and archivist.db_schema in config.toml."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from llm_archivist import Classifier as ArchivistClassifier
from llm_archivist import ClassifyOpts, Decision, Workflow

from mailflow.config import Config, ConfigurationError

_classifier: Optional[ArchivistClassifier] = None
_config: Optional[Config] = None


def set_config(config: Config) -> None:
    """Set the config instance for archivist client.

    Must be called before using classify/feedback functions.
    This is typically done during application startup.
    """
    global _config
    _config = config


async def _get_classifier() -> ArchivistClassifier:
    """Get or create the classifier with async DB initialization."""
    global _classifier
    if _classifier is None:
        # First check config, then fall back to env var for backward compat
        database_url = None
        db_schema = None

        if _config is not None:
            archivist = _config.settings.get("archivist", {})
            database_url = archivist.get("database_url")
            db_schema = archivist.get("db_schema")

        # Fall back to env vars if not in config
        if not database_url:
            database_url = os.getenv("DATABASE_URL")
        if not db_schema:
            db_schema = os.getenv("ARCHIVIST_DB_SCHEMA")

        if not database_url:
            raise ConfigurationError(
                "Archivist database_url not configured.\n"
                "Add to ~/.config/docflow/config.toml:\n\n"
                "[archivist]\n"
                'database_url = "postgresql://user:pass@localhost:5432/docflow"\n'
                'db_schema = "archivist"\n'
            )

        # Set env var for llm-archivist to pick up
        os.environ["DATABASE_URL"] = database_url
        if db_schema:
            os.environ["ARCHIVIST_DB_SCHEMA"] = db_schema

        _classifier = await ArchivistClassifier.from_env_async()
    return _classifier


async def classify(
    text: str,
    meta: Dict[str, Any],
    workflows: List[Workflow],
    opts: Optional[ClassifyOpts] = None,
    pdf_path: Optional[str] = None,
) -> Decision:
    """Classify using archivist. Must be awaited within an event loop."""
    clf = await _get_classifier()
    return await clf.classify_async(text, meta, workflows, opts=opts, pdf_path=pdf_path)


async def feedback(decision_id: int, label: str, reason: str | None = None) -> None:
    """Record feedback for a prior decision. Must be awaited."""
    clf = await _get_classifier()
    await clf.feedback_async(int(decision_id), label, reason)


async def get_metrics() -> Dict[str, Any]:
    """Return basic metrics from archivist. Must be awaited."""
    clf = await _get_classifier()
    return await clf.get_metrics_async()
