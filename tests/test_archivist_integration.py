# ABOUTME: Unit tests for llm-archivist adapter integration without network.

from mailflow.archivist_integration import classify_with_archivist, _build_workflows


class _WF:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description


class _DS:
    def __init__(self):
        self.workflows = {
            "invoices": _WF("invoices", "Save invoices and receipts"),
            "hr": _WF("hr", "Recruiting documents"),
        }


def test_build_workflows_from_datastore():
    ds = _DS()
    wfs = _build_workflows(ds)
    names = {w["name"] for w in wfs}
    assert names == {"invoices", "hr"}


class _FakeClassifier:
    def __init__(self, decision):
        self._decision = decision

    def classify(self, text, meta, workflows, opts=None):
        return self._decision


def test_classify_with_archivist_adapter_maps_candidates():
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
    result = classify_with_archivist(email, ds, classifier=fake)
    assert result["label"] == "invoices"
    assert result["rankings"][0][0] == "invoices"
    assert isinstance(result["rankings"][0][1], float)

