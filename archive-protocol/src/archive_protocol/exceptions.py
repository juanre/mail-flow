# ABOUTME: Custom exception hierarchy for archive-protocol
# ABOUTME: Provides specialized exceptions with recovery hints for archive operations


class ArchiveError(Exception):
    """Base exception for archive-protocol errors."""
    def __init__(self, message: str, recovery_hint: str | None = None):
        self.message = message
        self.recovery_hint = recovery_hint
        super().__init__(message)


class ValidationError(ArchiveError):
    """Validation error for metadata or input."""
    pass


class WriteError(ArchiveError):
    """Error during file write operations."""
    pass


class PathError(ArchiveError):
    """Error resolving or validating paths."""
    pass
