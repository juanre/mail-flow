from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from mailflow.email_extractor import EmailExtractor
from mailflow.workflow import save_attachment


def test_convert_text_attachment_to_pdf(temp_config_with_llmemory):
    msg = MIMEMultipart()
    msg["From"] = "sender@example.com"
    msg["Subject"] = "Notes"
    msg.attach(MIMEText("See attached notes", "plain"))

    att = MIMEBase("text", "plain")
    content = b"These are the notes."
    att.set_payload(content)
    encoders.encode_base64(att)
    att.add_header("Content-Disposition", 'attachment; filename="notes.txt"')
    msg.attach(att)

    extractor = EmailExtractor()
    email_data = extractor.extract(msg.as_string())

    config = temp_config_with_llmemory
    cfg = config.settings["archive"]
    cfg["layout"] = "v2"
    cfg["convert_attachments"] = True

    result = save_attachment(message=email_data, workflow="acme-notes", config=config)
    assert result["success"] and result["count"] == 1
    path = Path(result["documents"][0]["content_path"])
    assert path.suffix == ".pdf"
    # Basic PDF header check
    assert path.read_bytes().startswith(b"%PDF")


def test_keep_csv_as_csv(temp_config_with_llmemory):
    msg = MIMEMultipart()
    msg["From"] = "sender@example.com"
    msg["Subject"] = "Data"
    msg.attach(MIMEText("See attached CSV", "plain"))

    att = MIMEBase("text", "csv")
    content = b"col1,col2\n1,2\n"
    att.set_payload(content)
    encoders.encode_base64(att)
    att.add_header("Content-Disposition", 'attachment; filename="data.csv"')
    msg.attach(att)

    extractor = EmailExtractor()
    email_data = extractor.extract(msg.as_string())

    config = temp_config_with_llmemory
    cfg = config.settings["archive"]
    cfg["layout"] = "v2"
    cfg["convert_attachments"] = True

    result = save_attachment(message=email_data, workflow="acme-data", config=config)
    assert result["success"] and result["count"] == 1
    path = Path(result["documents"][0]["content_path"])
    assert path.suffix == ".csv"
    assert path.read_bytes() == content


def test_convert_tsv_to_csv(temp_config_with_llmemory):
    msg = MIMEMultipart()
    msg["From"] = "sender@example.com"
    msg["Subject"] = "Data TSV"
    msg.attach(MIMEText("See attached TSV", "plain"))

    att = MIMEBase("text", "tab-separated-values")
    content = b"col1\tcol2\n1\t2\n"
    att.set_payload(content)
    encoders.encode_base64(att)
    att.add_header("Content-Disposition", 'attachment; filename="data.tsv"')
    msg.attach(att)

    extractor = EmailExtractor()
    email_data = extractor.extract(msg.as_string())

    config = temp_config_with_llmemory
    cfg = config.settings["archive"]
    cfg["layout"] = "v2"
    cfg["convert_attachments"] = True

    result = save_attachment(message=email_data, workflow="acme-data", config=config)
    assert result["success"] and result["count"] == 1
    path = Path(result["documents"][0]["content_path"])
    assert path.suffix == ".csv"
    assert path.read_bytes() == b"col1,col2\n1,2\n"
