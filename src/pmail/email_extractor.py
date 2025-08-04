import email
import re
from typing import Dict, List, Any, Optional
from email.message import Message
import mimetypes


class EmailExtractor:
    def __init__(self):
        pass
        
    def extract(self, message_text: str) -> Dict[str, Any]:
        msg = email.message_from_string(message_text)
        
        extracted = {
            "from": self._clean_address(msg.get("from", "")),
            "to": self._clean_address(msg.get("to", "")),
            "subject": self._clean_subject(msg.get("subject", "")),
            "message_id": self._clean_message_id(msg.get("message-id", "")),
            "date": msg.get("date", ""),
            "body": "",
            "attachments": [],
            "features": {}
        }
        
        body_text = self._extract_body(msg)
        extracted["body"] = self._clean_body(body_text)
        extracted["attachments"] = self._extract_attachments(msg)
        extracted["features"] = self._extract_features(extracted)
        
        return extracted
    
    def _clean_address(self, address: str) -> str:
        return address.strip() if address else ""
    
    def _clean_subject(self, subject: str) -> str:
        if not subject:
            return ""
        subject = subject.strip()
        subject = subject.replace("/", "-").replace("[", "(").replace("]", ")")
        return subject
    
    def _clean_message_id(self, message_id: str) -> str:
        if not message_id:
            return ""
        message_id = message_id.strip()
        if message_id.startswith("<") and message_id.endswith(">"):
            message_id = message_id[1:-1]
        return message_id
    
    def _clean_body(self, body: str) -> str:
        if not body:
            return ""
        return body.replace("/", "-")
    
    def _extract_body(self, msg: Message) -> str:
        body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                cdispo = str(part.get("Content-Disposition", ""))
                
                if ctype == "text/plain" and "attachment" not in cdispo:
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode('utf-8', 'ignore')
                            break
                    except:
                        body = part.get_payload()
                        break
                elif ctype == "text/html" and not body and "attachment" not in cdispo:
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = self._html_to_text(payload.decode('utf-8', 'ignore'))
                    except:
                        body = part.get_payload()
        else:
            if msg.get_content_type() == "text/html":
                try:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = self._html_to_text(payload.decode('utf-8', 'ignore'))
                except:
                    body = msg.get_payload()
            else:
                try:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode('utf-8', 'ignore')
                except:
                    body = msg.get_payload()
        
        return body
    
    def _html_to_text(self, html: str) -> str:
        try:
            from html2text import html2text
            return html2text(html)
        except ImportError:
            import re
            text = re.sub(r'<[^>]+>', '', html)
            text = re.sub(r'\s+', ' ', text)
            return text.strip()
    
    def _extract_attachments(self, msg: Message) -> List[Dict[str, Any]]:
        attachments = []
        
        if msg.is_multipart():
            for part in msg.walk():
                cdispo = part.get("Content-Disposition", "")
                if "attachment" in cdispo:
                    filename = part.get_filename()
                    if filename:
                        att_info = {
                            "filename": filename,
                            "content_type": part.get_content_type(),
                            "size": len(part.get_payload())
                        }
                        
                        ext = filename.split('.')[-1].lower() if '.' in filename else ''
                        att_info["extension"] = ext
                        att_info["is_pdf"] = ext == "pdf"
                        att_info["is_image"] = ext in ["jpg", "jpeg", "png", "gif", "bmp"]
                        att_info["is_document"] = ext in ["pdf", "doc", "docx", "xls", "xlsx"]
                        
                        attachments.append(att_info)
        
        return attachments
    
    def _extract_features(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        features = {}
        
        from_addr = email_data["from"]
        if "@" in from_addr:
            if "<" in from_addr and ">" in from_addr:
                email_part = from_addr[from_addr.find("<")+1:from_addr.find(">")]
            else:
                email_part = from_addr
            features["from_domain"] = email_part.split("@")[1].lower()
        else:
            features["from_domain"] = ""
        
        features["has_pdf"] = any(att["is_pdf"] for att in email_data["attachments"])
        features["has_attachments"] = len(email_data["attachments"]) > 0
        features["num_attachments"] = len(email_data["attachments"])
        features["has_images"] = any(att["is_image"] for att in email_data["attachments"])
        features["has_documents"] = any(att["is_document"] for att in email_data["attachments"])
        
        subject_lower = email_data["subject"].lower()
        body_lower = email_data["body"].lower()[:1000]
        
        # Extract generic keywords from subject and body for similarity matching
        features["subject_words"] = list(set(re.findall(r'\b\w+\b', subject_lower)))
        features["body_preview_words"] = list(set(re.findall(r'\b\w+\b', body_lower)))
        
        features["subject_length"] = len(email_data["subject"])
        features["body_length"] = len(email_data["body"])
        
        return features