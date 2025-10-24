"""Test attachment extraction functionality"""

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from mailflow.attachment_handler import extract_attachments


class TestAttachmentHandler:
    def create_test_message_with_attachment(self):
        """Create a test email with PDF attachment"""
        msg = MIMEMultipart()
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Subject"] = "Test with attachment"

        # Add body
        body = MIMEText("This email has an attachment")
        msg.attach(body)

        # Add PDF attachment
        attachment = MIMEBase("application", "pdf")
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        attachment.set_payload(pdf_content)
        encoders.encode_base64(attachment)
        attachment.add_header("Content-Disposition", 'attachment; filename="test_document.pdf"')
        msg.attach(attachment)

        return msg, pdf_content

    def test_extract_attachments_single_pdf(self):
        """Test extracting a single PDF attachment"""
        msg, pdf_content = self.create_test_message_with_attachment()

        attachments = extract_attachments(msg, pattern="*.pdf")

        assert len(attachments) == 1
        filename, content, mimetype = attachments[0]
        assert filename == "test_document.pdf"
        assert content == pdf_content
        assert mimetype == "application/pdf"

    def test_extract_attachments_with_pattern(self):
        """Test extracting attachments with pattern matching"""
        msg = MIMEMultipart()
        msg["From"] = "sender@example.com"

        # Add multiple attachments with different types
        attachments_data = [
            ("document.pdf", b"%PDF-1.4\nfake pdf", "application/pdf"),
            ("image.jpg", b"\xff\xd8\xff", "image/jpeg"),
            ("data.csv", b"col1,col2\nval1,val2", "text/csv"),
        ]

        for filename, content, content_type in attachments_data:
            att = MIMEBase(*content_type.split("/"))
            att.set_payload(content)
            att.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(att)

        # Extract only PDFs
        pdf_attachments = extract_attachments(msg, pattern="*.pdf")
        assert len(pdf_attachments) == 1
        assert pdf_attachments[0][0] == "document.pdf"

        # Extract only images
        image_attachments = extract_attachments(msg, pattern="*.jpg")
        assert len(image_attachments) == 1
        assert image_attachments[0][0] == "image.jpg"

        # Extract all
        all_attachments = extract_attachments(msg, pattern="*")
        assert len(all_attachments) == 3

    def test_extract_attachments_no_attachments(self):
        """Test extracting from email with no attachments"""
        msg = MIMEMultipart()
        msg["From"] = "sender@example.com"
        msg.attach(MIMEText("Just a text body"))

        attachments = extract_attachments(msg, pattern="*.pdf")
        assert len(attachments) == 0

    def test_extract_attachments_returns_bytes(self):
        """Test that extract_attachments returns actual bytes, not encoded"""
        msg = MIMEMultipart()
        msg["From"] = "sender@example.com"

        # Add PDF attachment
        pdf_content = b"%PDF-1.4\nTest PDF content"
        att = MIMEBase("application", "pdf")
        att.set_payload(pdf_content)
        encoders.encode_base64(att)  # This encodes the payload
        att.add_header("Content-Disposition", 'attachment; filename="test.pdf"')
        msg.attach(att)

        # Extract should return decoded bytes
        attachments = extract_attachments(msg, pattern="*.pdf")
        assert len(attachments) == 1
        filename, content, mimetype = attachments[0]

        # Verify we got the original bytes, not base64 encoded
        assert content == pdf_content
        assert content.startswith(b"%PDF")

    def test_extract_attachments_multiple_pdfs(self):
        """Test extracting multiple PDF attachments"""
        msg = MIMEMultipart()
        msg["From"] = "sender@example.com"

        # Add three PDF attachments
        pdf_files = [
            ("invoice1.pdf", b"%PDF-1.4\nInvoice 1"),
            ("invoice2.pdf", b"%PDF-1.4\nInvoice 2"),
            ("receipt.pdf", b"%PDF-1.4\nReceipt"),
        ]

        for filename, content in pdf_files:
            att = MIMEBase("application", "pdf")
            att.set_payload(content)
            att.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(att)

        attachments = extract_attachments(msg, pattern="*.pdf")

        assert len(attachments) == 3
        filenames = [att[0] for att in attachments]
        assert "invoice1.pdf" in filenames
        assert "invoice2.pdf" in filenames
        assert "receipt.pdf" in filenames

    def test_extract_attachments_preserves_mimetype(self):
        """Test that mimetype is correctly extracted"""
        msg = MIMEMultipart()
        msg["From"] = "sender@example.com"

        # Add different types of attachments
        test_files = [
            ("doc.pdf", b"PDF", "application/pdf"),
            ("image.png", b"PNG", "image/png"),
            ("sheet.xlsx", b"XLSX", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ]

        for filename, content, mimetype in test_files:
            maintype, subtype = mimetype.split("/")
            att = MIMEBase(maintype, subtype)
            att.set_payload(content)
            att.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(att)

        # Extract all and verify mimetypes
        attachments = extract_attachments(msg, pattern="*")

        for i, (filename, content, extracted_mimetype) in enumerate(attachments):
            expected_mimetype = test_files[i][2]
            assert extracted_mimetype == expected_mimetype
