from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email import encoders

from mailflow.email_extractor import EmailExtractor
from mailflow.attachment_handler import save_attachments_from_message


def test_attachment_original_filename_and_size(temp_config_dir):
    # Build an email with a PDF attachment
    msg = MIMEMultipart()
    msg["From"] = "sender@example.com"
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

    # Save and persist metadata
    saved = save_attachments_from_message(
        message_obj=email_data["_message_obj"],
        email_data=email_data,
        directory=temp_config_dir,
        pattern="*.pdf",
        store_metadata=True,
        use_year_dirs=False,
    )
    assert saved == 1
