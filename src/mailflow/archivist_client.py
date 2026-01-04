"""Async client for the llm-archivist Classifier.

Always uses database mode for persistent learning.
Requires archivist.database_url and archivist.db_schema in config.toml.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from llm_archivist import Classifier as ArchivistClassifier
from llm_archivist import ClassifyOpts, Decision, Workflow
from llm_archivist.config import ArchivistConfig

from mailflow.config import Config, ConfigurationError

_classifier: Optional[ArchivistClassifier] = None
_classifier_lock = asyncio.Lock()
_config: Optional[Config] = None


def set_config(config: Config) -> None:
    """Set the config instance for archivist client.

    Must be called before using classify/feedback functions.
    This is typically done during application startup.

    Args:
        config: Config instance with archivist settings

    Note:
        Calling this multiple times will update the config reference.
        However, if classifier is already initialized, it won't
        reinitialize with new config automatically.
    """
    global _config
    _config = config


async def _get_classifier() -> ArchivistClassifier:
    """Get or create the classifier with async DB initialization.

    Uses double-checked locking to prevent race conditions in async context.
    """
    global _classifier
    if _classifier is None:
        async with _classifier_lock:
            # Double-check after acquiring lock
            if _classifier is None:
                _classifier = await _initialize_classifier()
    return _classifier


async def _initialize_classifier() -> ArchivistClassifier:
    """Initialize the classifier with config."""
    if _config is None:
        raise ConfigurationError("Archivist client config not set (call set_config).")

    archivist = _config.settings.get("archivist", {})
    database_url = archivist.get("database_url")
    db_schema = archivist.get("db_schema")
    similarity_threshold = archivist.get("similarity_threshold")

    if not database_url or not db_schema:
        config_path = _config.config_dir / "config.toml"
        raise ConfigurationError(
            "Archivist database_url/db_schema not configured.\n\n"
            f"Add to {config_path}:\n"
            "[archivist]\n"
            'database_url = "postgresql://user:pass@localhost:5432/docflow"\n'
            'db_schema = "archivist"\n'
        )

    if similarity_threshold is None:
        raise ConfigurationError("archivist.similarity_threshold is required in config.toml")

    if not database_url.startswith(("postgresql://", "postgres://")):
        raise ConfigurationError(
            "Invalid database URL format. Expected postgresql:// or postgres:// URL."
        )

    cfg = ArchivistConfig(
        database_url=database_url,
        db_schema=db_schema,
        similarity_threshold=float(similarity_threshold),
    )
    return await ArchivistClassifier.from_config_async(cfg)


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
