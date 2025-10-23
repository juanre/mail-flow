# ABOUTME: Package initialization for mailflow email processing system
# ABOUTME: Defines version and sets up package-level logging configuration
"""mailflow - Smart Email Processing for Mutt"""

__version__ = "0.2.0"

# Set up logging for the package
import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())
