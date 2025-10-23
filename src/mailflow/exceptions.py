# ABOUTME: Custom exception hierarchy for mailflow error handling
# ABOUTME: Provides specialized exceptions with recovery hints for each module
"""Custom exceptions for mailflow"""


class MailflowError(Exception):
    """Base exception for all mailflow errors"""

    def __init__(self, message: str, recovery_hint: str | None = None):
        super().__init__(message)
        self.recovery_hint = recovery_hint

    def __str__(self):
        base = super().__str__()
        if self.recovery_hint:
            return f"{base}\nHint: {self.recovery_hint}"
        return base


class ConfigError(MailflowError):
    """Configuration related errors"""

    pass


class DataError(MailflowError):
    """Data storage/retrieval errors"""

    pass


class WorkflowError(MailflowError):
    """Workflow execution errors"""

    pass


class EmailParsingError(MailflowError):
    """Email parsing errors"""

    pass


class SimilarityError(MailflowError):
    """Similarity calculation errors"""

    pass


class UIError(MailflowError):
    """User interface errors"""

    pass


class ValidationError(MailflowError):
    """Validation errors"""

    pass
