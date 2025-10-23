# ABOUTME: Logging configuration setup for mailflow application
# ABOUTME: Configures console and file logging with rotation and exception handling
import logging
import logging.handlers
import os
from pathlib import Path

from mailflow.config import Config


def setup_logging(
    log_level: str = "INFO",
    log_file: str | None = None,
    log_dir: str | None = None,
) -> None:
    """
    Set up logging configuration for mailflow.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Log file name (if None, logs to stderr only)
        log_dir: Directory for log files (if None, uses XDG state directory)
    """
    # Create logger
    logger = logging.getLogger("mailflow")
    logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    logger.handlers.clear()

    # Create formatters
    detailed_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    simple_formatter = logging.Formatter("%(levelname)s: %(message)s")

    # Console handler (stderr)
    console_handler = logging.StreamHandler()
    # Reflect requested log level on console output
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_handler.setFormatter(simple_formatter)
    logger.addHandler(console_handler)

    # File handler (if requested)
    if log_file:
        if log_dir is None:
            config = Config()
            log_path = config.get_log_dir()
        else:
            log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        file_path = log_path / log_file

        # Use rotating file handler to prevent unbounded growth
        file_handler = logging.handlers.RotatingFileHandler(
            file_path, maxBytes=10 * 1024 * 1024, backupCount=5  # 10MB
        )
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(detailed_formatter)
        logger.addHandler(file_handler)

    # Log uncaught exceptions
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            # Don't log keyboard interrupt
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    import sys

    sys.excepthook = handle_exception

    # Log startup
    logger.debug(f"Logging initialized at {log_level} level")
