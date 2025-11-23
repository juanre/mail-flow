import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from email.mime.base import MIMEBase
from pathlib import Path

from mailflow.config import Config
from mailflow.email_extractor import EmailExtractor
from mailflow.workflow import save_pdf


def test_classifier_origin_fields(temp_config_dir):
    msg = MIMEMultipart()
    msg["From"] = "billing@vendor.com"
    msg["Subject"] = "Invoice 1234"
    msg.attach(MIMEText("See attached.", "plain"))
    content = b"%PDF-1.4\n..."
    att = MIMEBase("application", "pdf")
    att.set_payload(content)
    encoders.encode_base64(att)
    att.add_header("Content-Disposition", 'attachment; filename="invoice_1234.pdf"')
    msg.attach(att)

    extractor = EmailExtractor()
    email_data = extractor.extract(msg.as_string())

    config = Config(config_dir=temp_config_dir)
    archive_path = Path(temp_config_dir) / "Archive"
    cfg = config.settings["archive"]
    cfg["base_path"] = str(archive_path)
    cfg["layout"] = "v2"
    # Enable classifier
    config.settings.setdefault("classifier", {})["enabled"] = True

    result = save_pdf(message=email_data, workflow="acme-invoice", config=config)
    assert result["success"] and result["count"] == 1
    meta_path = Path(result["documents"][0]["metadata_path"])
    data = json.loads(meta_path.read_text())
    clf = data["origin"].get("classifier")
    assert clf is not None
    assert "type" in clf and "confidence" in clf

