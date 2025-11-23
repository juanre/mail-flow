# ABOUTME: Integration helpers to use llm-archivist for workflow classification
# ABOUTME: Builds inputs (text + metadata) and maps results into mailflow structures.

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _build_text(email_data: dict) -> str:
    subject = (email_data.get("subject") or "").strip()
    body = (email_data.get("body") or "")[:1000]
    return f"Subject: {subject}\n\n{body}".strip()


def _build_meta(email_data: dict) -> dict:
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


def _build_workflows(data_store) -> List[dict]:
    workflows: List[dict] = []
    for name, wf in (data_store.workflows or {}).items():
        # wf is WorkflowDefinition
        workflows.append({
            "name": name,
            "description": getattr(wf, "description", name) or name,
            "tags": [],
        })
    return workflows


def classify_with_archivist(
    email_data: dict,
    data_store,
    *,
    interactive: bool = True,
    allow_llm: bool = True,
    max_candidates: int = 5,
    classifier: Optional[Any] = None,
) -> dict:
    """
    Run llm-archivist classification and return a mailflow-compatible result.

    Returns a dict with keys: label, confidence, candidates (list of {label, confidence, source}).
    """
    text = _build_text(email_data)
    meta = _build_meta(email_data)
    workflows = _build_workflows(data_store)
    if not workflows:
        return {"label": None, "confidence": 0.0, "candidates": []}

    if classifier is None:
        # Lazy import to avoid hard dependency when disabled
        try:
            from llm_archivist import Classifier as _ArchClassifier  # type: ignore
        except Exception:
            return {"label": None, "confidence": 0.0, "candidates": []}
        classifier = _ArchClassifier.from_env()

    opts: Dict[str, Any] = {
        "allow_llm": bool(allow_llm),
        "interactive": bool(interactive),
        "max_candidates": int(max_candidates),
    }
    decision = classifier.classify(text, meta, workflows, opts=opts)

    # Map to rankings-compatible structure
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


def record_feedback(decision_id: int, label: str, reason: str | None = None) -> None:
    """Send feedback to llm-archivist if available."""
    try:
        from llm_archivist import Classifier as _ArchClassifier  # type: ignore
    except Exception:
        return
    clf = _ArchClassifier.from_env()
    try:
        clf.feedback(int(decision_id), str(label), reason)
    except Exception:
        # Non-fatal; keep UI responsive
        pass
