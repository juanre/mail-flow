"""Async client for the llm-archivist Classifier.

Always uses database mode for persistent learning.
Requires archivist.database_url and archivist.db_schema in config.toml.

Security Note: Database credentials are passed via environment variables
to llm-archivist, as required by its API. These credentials will be
visible to child processes spawned by this application.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

from llm_archivist import Classifier as ArchivistClassifier
from llm_archivist import ClassifyOpts, Decision, Workflow

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
    """Initialize the classifier with config or env vars."""
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
            "Archivist database_url not configured.\n\n"
            "Option 1: Add to ~/.config/docflow/config.toml:\n"
            "[archivist]\n"
            'database_url = "postgresql://user:pass@localhost:5432/docflow"\n'
            'db_schema = "archivist"\n\n'
            "Option 2: Set environment variables:\n"
            "  export DATABASE_URL='postgresql://...'\n"
            "  export ARCHIVIST_DB_SCHEMA='archivist'\n"
        )

    # Validate URL format
    if not database_url.startswith(('postgresql://', 'postgres://')):
        raise ConfigurationError(
            f"Invalid database URL format.\n"
            f"Expected postgresql:// or postgres:// URL"
        )

    # Set env var for llm-archivist to pick up (required by its API)
    os.environ["DATABASE_URL"] = database_url
    if db_schema:
        os.environ["ARCHIVIST_DB_SCHEMA"] = db_schema

    return await ArchivistClassifier.from_env_async()


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
