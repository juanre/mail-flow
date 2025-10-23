import shutil
import tempfile

import pytest

from mailflow.config import Config


@pytest.fixture
def temp_config_dir():
    """Create a temporary config directory for tests"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def test_config(temp_config_dir):
    """Create a test config instance"""
    return Config(config_dir=temp_config_dir)


@pytest.fixture
def sample_email():
    """Sample email for testing"""
    return """From: test@example.com
To: user@mydomain.com
Subject: Test Email with Invoice
Date: Mon, 1 Mar 2024 10:00:00 -0000
Message-ID: <test123@example.com>
Content-Type: text/plain

This is a test email about an invoice.

Best regards,
Test Sender
"""


@pytest.fixture
def sample_email_with_attachment():
    """Sample email with attachment"""
    return """From: sender@company.com
To: recipient@example.com
Subject: Report for Q1 2024
Date: Mon, 1 Mar 2024 10:00:00 -0000
Message-ID: <report123@company.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="boundary123"

--boundary123
Content-Type: text/plain

Please find the Q1 report attached.

--boundary123
Content-Type: application/pdf
Content-Disposition: attachment; filename="report_q1_2024.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKJeLjz9MKCg==

--boundary123--
"""
