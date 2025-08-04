"""Custom exceptions for pmail"""

from typing import Optional


class PmailError(Exception):
    """Base exception for all pmail errors"""

    def __init__(self, message: str, recovery_hint: Optional[str] = None):
        super().__init__(message)
        self.recovery_hint = recovery_hint

    def __str__(self):
        base = super().__str__()
        if self.recovery_hint:
            return f"{base}\nHint: {self.recovery_hint}"
        return base


class ConfigError(PmailError):
    """Configuration related errors"""

    pass


class DataError(PmailError):
    """Data storage/retrieval errors"""

    pass


class WorkflowError(PmailError):
    """Workflow execution errors"""

    pass


class EmailParsingError(PmailError):
    """Email parsing errors"""

    pass


class SimilarityError(PmailError):
    """Similarity calculation errors"""

    pass


class UIError(PmailError):
    """User interface errors"""

    pass


class ValidationError(PmailError):
    """Validation errors"""

    pass
