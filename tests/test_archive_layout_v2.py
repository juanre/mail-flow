from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from email.mime.base import MIMEBase
from pathlib import Path

from mailflow.config import Config
from mailflow.email_extractor import EmailExtractor
from mailflow.workflow import save_pdf


def test_layout_v2_docs_and_originals(temp_config_dir):
    # Email with one PDF attachment
    msg = MIMEMultipart()
    msg["From"] = "billing@vendor.com"
    msg["To"] = "user@example.com"
    msg["Subject"] = "Invoice ABC"
    msg["Date"] = "Wed, 05 Nov 2025 10:00:00 +0000"

    msg.attach(MIMEText("Please find invoice attached.", "plain"))
    content = b"%PDF-1.4\n...."
    att = MIMEBase("application", "pdf")
    att.set_payload(content)
    encoders.encode_base64(att)
    att.add_header("Content-Disposition", 'attachment; filename="invoice_abc.pdf"')
    msg.attach(att)

    extractor = EmailExtractor()
    email_data = extractor.extract(msg.as_string())

    config = Config(config_dir=temp_config_dir)
    archive_path = Path(temp_config_dir) / "Archive"
    cfg = config.settings["archive"]
    cfg["base_path"] = str(archive_path)
    cfg["layout"] = "v2"
    cfg["save_originals"] = True
    cfg["originals_prefix_date"] = True

    result = save_pdf(message=email_data, workflow="acme-invoice", config=config)
    assert result["success"]

    # Check saved doc path uses {doctype}/{YYYY}/ and normalized name
    doc_path = Path(result["documents"][0]["content_path"])
    assert "/acme/invoice/2025/" in str(doc_path)
    assert doc_path.suffix == ".pdf"
    assert doc_path.read_bytes() == content

    # Check original exists under originals/{YYYY}/ with date prefix and original name preserved (case)
    originals_dir = archive_path / "acme" / "originals" / "2025"
    candidates = list(originals_dir.glob("2025-11-05-invoice_abc.pdf"))
    assert candidates, f"Original file not found in {originals_dir}"
    assert candidates[0].read_bytes() == content
