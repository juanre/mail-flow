# ABOUTME: Tests for email thread detection using References and In-Reply-To headers.
"""Tests for email thread detection."""

from mailflow.thread_detector import detect_threads, get_thread_info


class TestDetectThreads:
    def test_single_email_no_thread(self):
        emails = [{"message_id": "<msg1@test.com>", "references": "", "date": "2025-01-01"}]
        threads = detect_threads(emails)
        assert len(threads) == 1

    def test_reply_grouped_with_original(self):
        emails = [
            {"message_id": "<msg1@test.com>", "references": "", "date": "2025-01-01"},
            {"message_id": "<msg2@test.com>", "references": "<msg1@test.com>", "date": "2025-01-02"},
        ]
        threads = detect_threads(emails)
        assert len(threads) == 1
        assert len(list(threads.values())[0]) == 2

    def test_separate_threads_not_grouped(self):
        emails = [
            {"message_id": "<msg1@test.com>", "references": "", "date": "2025-01-01"},
            {"message_id": "<msg2@test.com>", "references": "", "date": "2025-01-02"},
        ]
        threads = detect_threads(emails)
        assert len(threads) == 2


class TestGetThreadInfo:
    def test_single_email_returns_none(self):
        emails = [{"message_id": "<msg1@test.com>", "references": "", "date": "2025-01-01"}]
        threads = detect_threads(emails)
        info = get_thread_info(emails[0], threads)
        assert info is None

    def test_thread_position_correct(self):
        emails = [
            {"message_id": "<msg1@test.com>", "references": "", "date": "2025-01-01"},
            {"message_id": "<msg2@test.com>", "references": "<msg1@test.com>", "date": "2025-01-02"},
            {"message_id": "<msg3@test.com>", "references": "<msg1@test.com>", "date": "2025-01-03"},
        ]
        threads = detect_threads(emails)
        info = get_thread_info(emails[1], threads)
        assert info.position == 2
        assert info.count == 3

    def test_pdf_hint_when_other_email_has_pdf(self):
        emails = [
            {"message_id": "<msg1@test.com>", "references": "", "date": "2025-01-01", "attachments": []},
            {"message_id": "<msg2@test.com>", "references": "<msg1@test.com>", "date": "2025-01-02",
             "attachments": [{"filename": "invoice.pdf"}]},
        ]
        threads = detect_threads(emails)
        info = get_thread_info(emails[0], threads)
        assert info.pdf_in_thread == 2  # PDF is in email 2
