import email
import re
from typing import Dict, List, Any, Optional
from email.message import Message
import mimetypes
import logging

from pmail.exceptions import EmailParsingError, ValidationError
from pmail.security import (
    MAX_EMAIL_SIZE_MB,
    MAX_SUBJECT_LENGTH,
    MAX_BODY_PREVIEW_LENGTH,
    MAX_ATTACHMENT_COUNT,
    sanitize_filename,
    validate_message_id,
)
from pmail.utils import truncate_string

logger = logging.getLogger(__name__)


class EmailExtractor:
    def __init__(self):
        self.max_email_size = MAX_EMAIL_SIZE_MB * 1024 * 1024  # Convert to bytes

    def extract(self, message_text: str) -> Dict[str, Any]:
        """Extract features from email with validation and size limits"""
        # Check email size
        if len(message_text) > self.max_email_size:
            raise EmailParsingError(
                f"Email too large: {len(message_text) / 1024 / 1024:.1f}MB "
                f"(max: {MAX_EMAIL_SIZE_MB}MB)",
                recovery_hint="Consider processing large emails differently",
            )

        try:
            msg = email.message_from_string(message_text)
        except Exception as e:
            raise EmailParsingError(
                f"Failed to parse email: {e}",
                recovery_hint="Check if the email format is valid",
            )

        extracted = {
            "from": self._clean_address(msg.get("from", "")),
            "to": self._clean_address(msg.get("to", "")),
            "subject": self._clean_subject(msg.get("subject", "")),
            "message_id": self._clean_message_id(msg.get("message-id", "")),
            "date": msg.get("date", ""),
            "body": "",
            "attachments": [],
            "features": {},
            "_message_obj": msg,  # Include the Message object for workflow use
        }

        # Extract body with size limit
        body_text = self._extract_body(msg)
        extracted["body"] = self._clean_body(body_text)

        # Extract attachments with count limit
        extracted["attachments"] = self._extract_attachments(msg)

        # Extract features for similarity matching
        extracted["features"] = self._extract_features(extracted)

        return extracted

    def _clean_address(self, address: str) -> str:
        """Clean and validate email address"""
        if not address:
            return ""

        # Truncate if too long
        return truncate_string(address.strip(), 500)

    def _clean_subject(self, subject: str) -> str:
        """Clean and validate subject"""
        if not subject:
            return ""

        subject = subject.strip()

        # Remove potentially dangerous characters
        subject = subject.replace("\n", " ").replace("\r", " ")

        # Replace file-system unfriendly characters
        subject = subject.replace("/", "-").replace("[", "(").replace("]", ")")

        # Truncate if too long
        return truncate_string(subject, MAX_SUBJECT_LENGTH)

    def _clean_message_id(self, message_id: str) -> str:
        """Clean and validate message ID"""
        if not message_id:
            return ""

        message_id = message_id.strip()

        # Remove angle brackets if present
        if message_id.startswith("<") and message_id.endswith(">"):
            message_id = message_id[1:-1]

        # Validate and sanitize
        return validate_message_id(message_id)

    def _clean_body(self, body: str) -> str:
        """Clean and truncate body text"""
        if not body:
            return ""

        # Remove potentially dangerous characters
        body = body.replace("\x00", "")  # Null bytes

        # Replace file-system unfriendly characters
        body = body.replace("/", "-")

        # Truncate for storage
        return truncate_string(body, MAX_BODY_PREVIEW_LENGTH * 2)

    def _extract_body(self, msg: Message) -> str:
        """Extract body text from email"""
        body = ""

        try:
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    cdispo = str(part.get("Content-Disposition", ""))

                    # Skip attachments
                    if "attachment" in cdispo:
                        continue

                    if ctype == "text/plain":
                        try:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode("utf-8", "ignore")
                                break
                        except Exception as e:
                            logger.warning(f"Failed to decode text/plain part: {e}")
                            body = str(part.get_payload())
                            break

                    elif ctype == "text/html" and not body:
                        try:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = self._html_to_text(payload.decode("utf-8", "ignore"))
                        except Exception as e:
                            logger.warning(f"Failed to decode text/html part: {e}")
            else:
                # Single part message
                if msg.get_content_type() == "text/html":
                    try:
                        payload = msg.get_payload(decode=True)
                        if payload:
                            body = self._html_to_text(payload.decode("utf-8", "ignore"))
                    except Exception as e:
                        logger.warning(f"Failed to decode HTML body: {e}")
                        body = str(msg.get_payload())
                else:
                    try:
                        payload = msg.get_payload(decode=True)
                        if payload:
                            body = payload.decode("utf-8", "ignore")
                    except Exception as e:
                        logger.warning(f"Failed to decode body: {e}")
                        body = str(msg.get_payload())

        except Exception as e:
            logger.error(f"Failed to extract body: {e}")
            body = ""

        return body

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to text"""
        try:
            # Try to use html2text if available
            from html2text import html2text

            return html2text(html)
        except ImportError:
            # Fallback to simple regex
            import re

            # Remove script and style elements
            html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
            # Remove HTML tags
            text = re.sub(r"<[^>]+>", " ", html)
            # Collapse whitespace
            text = re.sub(r"\s+", " ", text)
            return text.strip()

    def _extract_attachments(self, msg: Message) -> List[Dict[str, Any]]:
        """Extract attachment information with limits"""
        attachments = []

        if not msg.is_multipart():
            return attachments

        try:
            for part in msg.walk():
                cdispo = part.get("Content-Disposition", "")
                if "attachment" not in cdispo:
                    continue

                # Check attachment count limit
                if len(attachments) >= MAX_ATTACHMENT_COUNT:
                    logger.warning(f"Attachment limit ({MAX_ATTACHMENT_COUNT}) reached")
                    break

                filename = part.get_filename()
                if filename:
                    # Sanitize filename
                    safe_filename = sanitize_filename(filename)

                    att_info = {
                        "filename": safe_filename,
                        "original_filename": filename,
                        "content_type": part.get_content_type(),
                        "size": len(part.get_payload()),
                    }

                    # Extract extension safely
                    ext = ""
                    if "." in safe_filename:
                        ext = safe_filename.split(".")[-1].lower()

                    att_info["extension"] = ext
                    att_info["is_pdf"] = ext == "pdf"
                    att_info["is_image"] = ext in [
                        "jpg",
                        "jpeg",
                        "png",
                        "gif",
                        "bmp",
                        "webp",
                    ]
                    att_info["is_document"] = ext in [
                        "pdf",
                        "doc",
                        "docx",
                        "xls",
                        "xlsx",
                        "odt",
                        "ods",
                    ]

                    attachments.append(att_info)

        except Exception as e:
            logger.error(f"Failed to extract attachments: {e}")

        return attachments

    def _extract_features(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract features for similarity matching"""
        features = {}

        # Extract sender domain safely
        from_addr = email_data["from"]
        features["from_domain"] = ""
        if "@" in from_addr:
            try:
                # Handle "Name <email@domain>" format
                if "<" in from_addr and ">" in from_addr:
                    email_part = from_addr[from_addr.find("<") + 1 : from_addr.find(">")]
                else:
                    email_part = from_addr

                if "@" in email_part:
                    domain = email_part.split("@")[1].lower()
                    # Basic domain validation
                    if re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", domain):
                        features["from_domain"] = domain
            except Exception as e:
                logger.warning(f"Failed to extract domain: {e}")

        # Attachment features
        features["has_pdf"] = any(att.get("is_pdf", False) for att in email_data["attachments"])
        features["has_attachments"] = len(email_data["attachments"]) > 0
        features["num_attachments"] = len(email_data["attachments"])
        features["has_images"] = any(
            att.get("is_image", False) for att in email_data["attachments"]
        )
        features["has_documents"] = any(
            att.get("is_document", False) for att in email_data["attachments"]
        )

        # Text features with size limits
        subject_lower = email_data["subject"].lower()
        body_preview = email_data["body"][:MAX_BODY_PREVIEW_LENGTH].lower()

        # Extract keywords (limit number to prevent memory issues)
        features["subject_words"] = list(set(re.findall(r"\b\w+\b", subject_lower)))[:100]
        features["body_preview_words"] = list(set(re.findall(r"\b\w+\b", body_preview)))[:200]

        # Size features
        features["subject_length"] = len(email_data["subject"])
        features["body_length"] = len(email_data["body"])

        return features
