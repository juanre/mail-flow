import shutil
import tempfile
from pathlib import Path

import pytest

from mailflow.config import Config

# Import pgdbm test fixtures for real database testing
from pgdbm.fixtures.conftest import *

# Import llmemory test fixtures
from llmemory.testing import *


@pytest.fixture
def temp_config_dir():
    """Create a temporary config directory for tests"""
    temp_dir = tempfile.mkdtemp()
    workflows_file = Path(temp_dir) / "workflows.json"
    workflows_file.write_text('{"schema_version": 1, "workflows": []}')
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def temp_config_with_llmemory(temp_config_dir, memory_manager):
    """Create a test config with llmemory database configured.

    Uses real database from memory_manager fixture.
    """
    config_file = Path(temp_config_dir) / "config.toml"
    # Get the DSN from the memory_manager's database
    db_url = memory_manager.db.db_manager.config.get_dsn()

    config_file.write_text(f'''
[archive]
base_path = "{temp_config_dir}/Archive"

[llmemory]
database_url = "{db_url}"
''')

    # Create archive directory
    (Path(temp_config_dir) / "Archive").mkdir(exist_ok=True)

    return Config(config_dir=temp_config_dir)


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
