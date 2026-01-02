from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email import encoders
from pathlib import Path

from mailflow.email_extractor import EmailExtractor
from mailflow.workflow import save_attachment


def test_attachment_original_filename_and_size(temp_config_with_llmemory):
    # Build an email with a PDF attachment
    msg = MIMEMultipart()
    msg["From"] = "sender@example.com"
    msg["Message-ID"] = "<test123@example.com>"
    msg["Date"] = "Mon, 15 Jan 2024 10:00:00 +0000"
    pdf_att = MIMEBase("application", "pdf")
    raw = b"%PDF-1.4\ncontent"
    pdf_att.set_payload(raw)
    encoders.encode_base64(pdf_att)
    pdf_att.add_header("Content-Disposition", 'attachment; filename="Report Final.pdf"')
    msg.attach(pdf_att)

    extractor = EmailExtractor()
    email_data = extractor.extract(msg.as_string())

    # Ensure extractor preserved original filename and computed size
    assert email_data["attachments"][0]["original_filename"] == "Report Final.pdf"
    assert email_data["attachments"][0]["size"] > 0

    # Use config with archive and llmemory configured
    config = temp_config_with_llmemory

    # Save using archive-protocol workflow
    result = save_attachment(
        message=email_data,
        workflow="test-report",
        config=config,
        pattern="*.pdf"
    )

    assert result["success"]
    assert result["count"] == 1

    # Verify the original filename is preserved in metadata
    import json
    metadata_path = Path(result["documents"][0]["metadata_path"])
    with open(metadata_path, "r") as f:
        metadata = json.load(f)

    # Archive-protocol stores original filename in origin.attachment_filename
    assert "origin" in metadata
    assert metadata["origin"]["attachment_filename"] == "Report Final.pdf"
    assert metadata["type"] == "attachment"
