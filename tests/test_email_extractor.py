import pytest

from pmail.email_extractor import EmailExtractor


class TestEmailExtractor:
    def test_extract_basic_email(self, sample_email):
        extractor = EmailExtractor()
        result = extractor.extract(sample_email)

        assert result["from"] == "test@example.com"
        assert result["to"] == "user@mydomain.com"
        assert result["subject"] == "Test Email with Invoice"
        assert result["message_id"] == "test123@example.com"
        assert "test email about an invoice" in result["body"].lower()
        assert len(result["attachments"]) == 0

    def test_extract_features(self, sample_email):
        extractor = EmailExtractor()
        result = extractor.extract(sample_email)

        features = result["features"]
        assert features["from_domain"] == "example.com"
        assert features["has_pdf"] is False
        assert features["has_attachments"] is False
        assert features["num_attachments"] == 0
        assert "invoice" in features["subject_words"]
        assert isinstance(features["subject_words"], list)
        assert features["subject_length"] > 0
        assert features["body_length"] > 0

    def test_extract_email_with_attachment(self, sample_email_with_attachment):
        extractor = EmailExtractor()
        result = extractor.extract(sample_email_with_attachment)

        assert result["from"] == "sender@company.com"
        assert result["to"] == "recipient@example.com"
        assert len(result["attachments"]) == 1

        attachment = result["attachments"][0]
        assert attachment["filename"] == "report_q1_2024.pdf"
        assert attachment["is_pdf"] is True
        assert attachment["is_document"] is True
        assert attachment["extension"] == "pdf"

        features = result["features"]
        assert features["has_pdf"] is True
        assert features["has_attachments"] is True
        assert features["num_attachments"] == 1

    def test_clean_subject(self):
        extractor = EmailExtractor()

        # Test replacing special characters
        assert extractor._clean_subject("Test/Subject") == "Test-Subject"
        assert extractor._clean_subject("Test[Subject]") == "Test(Subject)"
        assert extractor._clean_subject("  Test Subject  ") == "Test Subject"

    def test_extract_from_domain(self):
        extractor = EmailExtractor()

        # Test various from formats
        test_cases = [
            ("user@example.com", "example.com"),
            ("User Name <user@example.com>", "example.com"),
            ('"User Name" <user@example.com>', "example.com"),
            ("user@subdomain.example.com", "subdomain.example.com"),
        ]

        for from_addr, expected_domain in test_cases:
            email_text = f"""From: {from_addr}
To: test@test.com
Subject: Test
Message-ID: <test@test.com>

Test body
"""
            result = extractor.extract(email_text)
            assert result["features"]["from_domain"] == expected_domain
