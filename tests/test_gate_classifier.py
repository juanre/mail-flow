from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from mailflow.config import Config
from mailflow.email_extractor import EmailExtractor
from mailflow.workflow import save_pdf


def test_gate_rejects_newsletter(temp_config_dir):
    msg = MIMEMultipart()
    msg["From"] = "no-reply@news.example.com"
    msg["Subject"] = "Weekly Newsletter"
    msg.attach(MIMEText("Unsubscribe at the bottom", "plain"))

    extractor = EmailExtractor()
    email_data = extractor.extract(msg.as_string())

    config = Config(config_dir=temp_config_dir)
    archive_path = Path(temp_config_dir) / "Archive"
    cfg = config.settings["archive"]
    cfg["base_path"] = str(archive_path)
    cfg["layout"] = "v2"
    # Enable classifier + gate
    config.settings.setdefault("classifier", {})["enabled"] = True
    config.settings["classifier"]["gate_enabled"] = True
    config.settings["classifier"]["gate_min_confidence"] = 0.7

    result = save_pdf(message=email_data, workflow="acme-misc", config=config)
    assert result.get("skipped") is True

    # Ensure no docs were written
    entity_docs = archive_path / "acme" / "docs"
    assert not entity_docs.exists() or not any(entity_docs.rglob("*.pdf"))


def test_gate_allows_invoice_like_email(temp_config_dir):
    msg = MIMEMultipart()
    msg["From"] = "billing@vendor.com"
    msg["Subject"] = "Invoice 5678"
    msg.attach(MIMEText("Please see invoice.", "plain"))

    extractor = EmailExtractor()
    email_data = extractor.extract(msg.as_string())

    config = Config(config_dir=temp_config_dir)
    archive_path = Path(temp_config_dir) / "Archive"
    cfg = config.settings["archive"]
    cfg["base_path"] = str(archive_path)
    cfg["layout"] = "v2"
    # Enable classifier + gate
    config.settings.setdefault("classifier", {})["enabled"] = True
    config.settings["classifier"]["gate_enabled"] = True

    result = save_pdf(message=email_data, workflow="acme-invoice", config=config)
    assert result.get("skipped") is not True
    assert result.get("success") is True
    # Check doc exists
    # result can be document_id/content_path form
    path = result.get("content_path") or (result.get("documents") or [{}])[0].get("content_path")
    assert path and Path(path).exists()

