# ABOUTME: Unit tests for llm-archivist adapter integration without network.

import os

import pytest
from mailflow.archivist_integration import classify_with_archivist, _build_workflows


class _WF:
    def __init__(self, name: str, summary: str, *, classifier: dict | None = None):
        self.name = name
        self.kind = "document"
        self.criteria = {"summary": summary}
        self.constraints = None
        self.classifier = classifier
        self.handling = {
            "archive": {"target": "document", "entity": "demo", "doctype": "doc"},
            "index": {"llmemory": True},
        }
        self.postprocessors = []


class _DS:
    def __init__(self):
        self.workflows = {
            "invoices": _WF(
                "invoices",
                "Save invoices and receipts",
                classifier={"appendix": "Expense workflow policy (TheStarMaps):\n\nReturn null for payment confirmations.\n"},
            ),
            "hr": _WF("hr", "Recruiting documents"),
        }


def test_build_workflows_from_datastore():
    ds = _DS()
    wfs = _build_workflows(ds)
    names = {w["name"] for w in wfs}
    assert names == {"invoices", "hr"}

def test_build_workflows_preserves_classifier_appendix_in_system_prompt():
    from llm_archivist.llm_advisor import _build_system_prompt, _normalize_workflows

    ds = _DS()
    workflow_payload = _build_workflows(ds)
    normalized = _normalize_workflows(workflow_payload)
    system = _build_system_prompt(normalized)

    assert "Workflow: invoices" in system
    assert "Expense workflow policy (TheStarMaps):" in system
    assert "Workflow: hr" not in system


class _FakeClassifier:
    def __init__(self, decision):
        self._decision = decision

    def classify(self, text, meta, workflows, opts=None, pdf_path=None):
        return self._decision


async def test_classify_with_archivist_adapter_maps_candidates():
    ds = _DS()
    email = {
        "from": "a@b.com",
        "to": "x@y.com",
        "subject": "invoice attached",
        "body": "please see attached invoice",
        "attachments": [],
        "message_id": "<1@x>",
        "date": "",
    }
    fake = _FakeClassifier(
        {
            "label": "invoices",
            "confidence": 0.91,
            "candidates": [
                {"label": "invoices", "confidence": 0.91, "source": "rules"},
                {"label": "hr", "confidence": 0.12, "source": "local"},
            ],
        }
    )
    result = await classify_with_archivist(email, ds, classifier=fake)
    assert result["label"] == "invoices"
    assert result["rankings"][0][0] == "invoices"
    assert isinstance(result["rankings"][0][1], float)


async def test_classify_prefers_pdf_attachment_for_llm_context(tmp_path):
    from email.mime.application import MIMEApplication
    from email.mime.multipart import MIMEMultipart

    ds = _DS()

    msg = MIMEMultipart()
    small_pdf = MIMEApplication(b"%PDF-1.4\nsmall\n", _subtype="pdf")
    small_pdf.add_header("Content-Disposition", "attachment", filename="small.pdf")
    big_pdf = MIMEApplication(b"%PDF-1.4\n" + (b"x" * 2048), _subtype="pdf")
    big_pdf.add_header("Content-Disposition", "attachment", filename="big.pdf")
    msg.attach(small_pdf)
    msg.attach(big_pdf)

    class _AssertingClassifier:
        def __init__(self):
            self.seen_pdf_path = None
            self.seen_pdf_size = None

        def classify(self, text, meta, workflows, opts=None, pdf_path=None):
            assert pdf_path is not None
            self.seen_pdf_path = pdf_path
            with open(pdf_path, "rb") as f:
                self.seen_pdf_size = len(f.read())
            return {"label": "invoices", "confidence": 0.9, "candidates": []}

    fake = _AssertingClassifier()
    email = {
        "from": "a@b.com",
        "to": "x@y.com",
        "subject": "invoice attached",
        "body": "see invoice",
        "attachments": [{"filename": "small.pdf", "is_pdf": True}, {"filename": "big.pdf", "is_pdf": True}],
        "_message_obj": msg,
        "message_id": "<1@x>",
        "date": "",
    }

    result = await classify_with_archivist(email, ds, classifier=fake)
    assert result["label"] == "invoices"
    assert fake.seen_pdf_size is not None
    assert fake.seen_pdf_size >= 2048
    assert fake.seen_pdf_path is not None
    # Temp files should be cleaned up by classify_with_archivist.
    assert not os.path.exists(fake.seen_pdf_path)
