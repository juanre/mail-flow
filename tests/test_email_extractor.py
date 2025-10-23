from mailflow.email_extractor import EmailExtractor


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

    def test_header_injection_subject(self):
        """Test that newlines and carriage returns are sanitized immediately after decoding"""
        extractor = EmailExtractor()

        # Test injection attempts in subject
        injection_attempts = [
            "Normal Subject\nInjected: Header",
            "Normal Subject\r\nInjected: Header",
            "Normal\nSubject\r\nWith\nMultiple\nLines",
            "Subject with\x00null bytes",
        ]

        for malicious_subject in injection_attempts:
            email_text = f"""From: test@example.com
To: user@test.com
Subject: {malicious_subject}
Message-ID: <test@test.com>

Test body
"""
            result = extractor.extract(email_text)

            # Newlines and carriage returns should be replaced with spaces
            assert "\n" not in result["subject"]
            assert "\r" not in result["subject"]
            # Null bytes should be removed
            assert "\x00" not in result["subject"]

    def test_header_injection_from_address(self):
        """Test that from addresses are sanitized to prevent header injection"""
        extractor = EmailExtractor()

        injection_attempts = [
            "attacker@evil.com\nBcc: victim@target.com",
            "attacker@evil.com\r\nBcc: victim@target.com",
            "Name\nInjected <attacker@evil.com>",
        ]

        for malicious_from in injection_attempts:
            email_text = f"""From: {malicious_from}
To: user@test.com
Subject: Test
Message-ID: <test@test.com>

Test body
"""
            result = extractor.extract(email_text)

            # Newlines and carriage returns should be sanitized
            assert "\n" not in result["from"]
            assert "\r" not in result["from"]

    def test_header_injection_to_address(self):
        """Test that to addresses are sanitized to prevent header injection"""
        extractor = EmailExtractor()

        injection_attempts = [
            "user@test.com\nBcc: victim@target.com",
            "user@test.com\r\nBcc: victim@target.com",
        ]

        for malicious_to in injection_attempts:
            email_text = f"""From: test@example.com
To: {malicious_to}
Subject: Test
Message-ID: <test@test.com>

Test body
"""
            result = extractor.extract(email_text)

            # Newlines and carriage returns should be sanitized
            assert "\n" not in result["to"]
            assert "\r" not in result["to"]

    def test_mime_encoded_header_injection(self):
        """Test that MIME-encoded headers with injection attempts are sanitized"""
        import base64

        extractor = EmailExtractor()

        # Create MIME-encoded subject with newline injection
        malicious_text = "Normal Subject\nInjected: Header\r\nAnother: Value"
        encoded = base64.b64encode(malicious_text.encode("utf-8")).decode("ascii")
        mime_subject = f"=?utf-8?B?{encoded}?="

        email_text = f"""From: test@example.com
To: user@test.com
Subject: {mime_subject}
Message-ID: <test@test.com>

Test body
"""
        result = extractor.extract(email_text)

        # After decoding and sanitization, newlines should be replaced with spaces
        assert "\n" not in result["subject"]
        assert "\r" not in result["subject"]
        assert "Normal Subject" in result["subject"]
        assert "Injected: Header" in result["subject"]

    def test_mime_encoded_address_injection(self):
        """Test that MIME-encoded addresses with injection attempts are sanitized"""
        import base64

        extractor = EmailExtractor()

        # Create MIME-encoded from address with newline injection
        malicious_text = "Sender Name\nBcc: victim@target.com"
        encoded = base64.b64encode(malicious_text.encode("utf-8")).decode("ascii")
        mime_from = f"=?utf-8?B?{encoded}?= <sender@example.com>"

        email_text = f"""From: {mime_from}
To: user@test.com
Subject: Test
Message-ID: <test@test.com>

Test body
"""
        result = extractor.extract(email_text)

        # After decoding and sanitization, newlines should be replaced with spaces
        assert "\n" not in result["from"]
        assert "\r" not in result["from"]
