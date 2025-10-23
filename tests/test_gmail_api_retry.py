# ABOUTME: Tests for Gmail API retry logic with exponential backoff
# ABOUTME: Validates transient error handling, backoff timing, and error recovery
"""Tests for Gmail API retry logic with exponential backoff."""

import time
from unittest.mock import Mock, patch, MagicMock

import pytest

from mailflow.config import Config
from mailflow.exceptions import EmailParsingError


@pytest.fixture
def mock_config(tmp_path):
    """Create a test config."""
    config = Config(config_dir=tmp_path)
    return config


@pytest.fixture
def mock_gmail_service():
    """Mock Gmail API service that returns up to 10 messages."""
    service = MagicMock()

    # Mock message list response - return up to 10 message IDs
    service.users().messages().list().execute.return_value = {
        "messages": [{"id": f"msg{i}"} for i in range(1, 11)]
    }

    # Mock raw message retrieval
    service.users().messages().get().execute.return_value = {
        "raw": "VGVzdCBlbWFpbCBjb250ZW50"  # base64 encoded "Test email content"
    }

    # Mock label list
    service.users().labels().list().execute.return_value = {
        "labels": [{"id": "label-id-1", "name": "mailflow/processed"}]
    }

    # Mock message modify
    service.users().messages().modify().execute.return_value = {}

    return service


class TestRetryLogic:
    """Test retry logic with exponential backoff."""

    @patch("mailflow.gmail_api.get_gmail_service")
    @patch("mailflow.gmail_api.process_email")
    def test_success_resets_transient_error_counter(
        self, mock_process, mock_get_service, mock_gmail_service, mock_config
    ):
        """Successful processing resets the transient error counter."""
        from mailflow.gmail_api import poll_and_process

        mock_get_service.return_value = mock_gmail_service

        # Configure to return only 3 messages
        mock_gmail_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg1"}, {"id": "msg2"}, {"id": "msg3"}]
        }

        # First message fails with transient error, second succeeds, third fails again
        # After first error, we continue to next message
        # After success, error counter resets, so third error is the first again
        mock_process.side_effect = [
            RuntimeError("Network error"),
            None,  # Success on msg2
            RuntimeError("Another network error"),
        ]

        with patch("mailflow.gmail_api.time.sleep"):  # Don't actually sleep in tests
            result = poll_and_process(mock_config, max_results=3)

        # Should process 1 message successfully (msg2)
        assert result == 1
        assert mock_process.call_count == 3

    @patch("mailflow.gmail_api.get_gmail_service")
    @patch("mailflow.gmail_api.process_email")
    def test_stops_after_max_consecutive_transient_errors(
        self, mock_process, mock_get_service, mock_gmail_service, mock_config
    ):
        """Processing stops after 3 consecutive transient errors."""
        from mailflow.gmail_api import poll_and_process

        mock_get_service.return_value = mock_gmail_service

        # All messages fail with transient errors
        mock_process.side_effect = RuntimeError("Network error")

        with patch("mailflow.gmail_api.time.sleep"):
            result = poll_and_process(mock_config, max_results=10)

        # Should stop after 3 consecutive errors
        assert result == 0
        assert mock_process.call_count == 3

    @patch("mailflow.gmail_api.get_gmail_service")
    @patch("mailflow.gmail_api.process_email")
    def test_parsing_errors_dont_count_as_transient(
        self, mock_process, mock_get_service, mock_gmail_service, mock_config
    ):
        """EmailParsingError is treated as permanent and doesn't increment transient counter."""
        from mailflow.gmail_api import poll_and_process

        mock_get_service.return_value = mock_gmail_service

        # Configure to return only 3 messages
        mock_gmail_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg1"}, {"id": "msg2"}, {"id": "msg3"}]
        }

        # Mix of parsing errors (permanent) and one success
        mock_process.side_effect = [
            EmailParsingError("Bad format"),
            EmailParsingError("Bad format"),
            None,  # Success
        ]

        with patch("mailflow.gmail_api.time.sleep"):
            result = poll_and_process(mock_config, max_results=3)

        # Should process 1 successfully, skip 2 parsing errors
        assert result == 1
        assert mock_process.call_count == 3

    @patch("mailflow.gmail_api.get_gmail_service")
    @patch("mailflow.gmail_api.process_email")
    def test_exponential_backoff_timing(
        self, mock_process, mock_get_service, mock_gmail_service, mock_config
    ):
        """Exponential backoff uses correct timing: 2^1, 2^2, 2^3 seconds."""
        from mailflow.gmail_api import poll_and_process

        mock_get_service.return_value = mock_gmail_service
        mock_process.side_effect = RuntimeError("Network error")

        with patch("mailflow.gmail_api.time.sleep") as mock_sleep:
            poll_and_process(mock_config, max_results=5)

            # Should sleep with exponential backoff: 2, 4 seconds
            # (doesn't sleep after third error because it stops)
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert sleep_calls == [2, 4]

    @patch("mailflow.gmail_api.get_gmail_service")
    @patch("mailflow.gmail_api.process_email")
    def test_backoff_resets_after_success(
        self, mock_process, mock_get_service, mock_gmail_service, mock_config
    ):
        """Backoff timing resets after successful processing."""
        from mailflow.gmail_api import poll_and_process

        mock_get_service.return_value = mock_gmail_service

        # Configure to return only 4 messages
        mock_gmail_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg1"}, {"id": "msg2"}, {"id": "msg3"}, {"id": "msg4"}]
        }

        # Error, Error, Success, Error
        mock_process.side_effect = [
            RuntimeError("Network error"),
            RuntimeError("Network error"),
            None,  # Success
            RuntimeError("Network error"),
        ]

        with patch("mailflow.gmail_api.time.sleep") as mock_sleep:
            result = poll_and_process(mock_config, max_results=4)

            # Should process 1 successfully
            assert result == 1

            # Sleep pattern: 2, 4 (for first two errors), then 2 (for error after success)
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert sleep_calls == [2, 4, 2]

    @patch("mailflow.gmail_api.get_gmail_service")
    @patch("mailflow.gmail_api.process_email")
    def test_empty_raw_content_doesnt_count_as_error(
        self, mock_process, mock_get_service, mock_gmail_service, mock_config
    ):
        """Messages with no raw content are skipped without incrementing error counter."""
        from mailflow.gmail_api import poll_and_process

        mock_get_service.return_value = mock_gmail_service

        # First message has no raw content
        mock_gmail_service.users().messages().get().execute.side_effect = [
            {"raw": ""},  # Empty raw
            {"raw": "VGVzdA=="},  # Valid
        ]

        mock_process.return_value = None

        result = poll_and_process(mock_config, max_results=2)

        # Should process 1 (the second message)
        assert result == 1
        assert mock_process.call_count == 1

    @patch("mailflow.gmail_api.get_gmail_service")
    @patch("mailflow.gmail_api.process_email")
    def test_label_modification_error_is_transient(
        self, mock_process, mock_get_service, mock_gmail_service, mock_config
    ):
        """Errors during label modification are treated as transient."""
        from mailflow.gmail_api import poll_and_process

        mock_get_service.return_value = mock_gmail_service
        mock_process.return_value = None  # Processing succeeds

        # Label modification fails
        mock_gmail_service.users().messages().modify().execute.side_effect = RuntimeError(
            "API error"
        )

        with patch("mailflow.gmail_api.time.sleep"):
            result = poll_and_process(mock_config, processed_label="mailflow/processed")

            # Should fail 3 times then stop
            assert result == 0

    @patch("mailflow.gmail_api.get_gmail_service")
    @patch("mailflow.gmail_api.process_email")
    def test_continues_processing_after_parsing_errors(
        self, mock_process, mock_get_service, mock_gmail_service, mock_config
    ):
        """Processing continues through multiple parsing errors without stopping."""
        from mailflow.gmail_api import poll_and_process

        mock_get_service.return_value = mock_gmail_service

        # Configure to return only 5 messages
        mock_gmail_service.users().messages().list().execute.return_value = {
            "messages": [{"id": f"msg{i}"} for i in range(1, 6)]
        }

        # Mix of parsing errors and successes - more than 3 parsing errors
        mock_process.side_effect = [
            EmailParsingError("Bad 1"),
            EmailParsingError("Bad 2"),
            EmailParsingError("Bad 3"),
            EmailParsingError("Bad 4"),
            None,  # Success
        ]

        result = poll_and_process(mock_config, max_results=5)

        # Should process 1 successfully, skip all parsing errors
        assert result == 1
        assert mock_process.call_count == 5
