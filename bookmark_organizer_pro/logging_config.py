"""Centralized logging system for the application.

Provides structured logging to both file and optional console output.
Singleton pattern ensures consistent logging throughout the application.
Set BOOKMARK_DEBUG=1 environment variable to enable console logging.
"""

import logging
import os
import sys

from .constants import LOG_FILE


class AppLogger:
    """Singleton logger for Bookmark Organizer Pro."""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if AppLogger._initialized:
            return

        AppLogger._initialized = True

        self.logger = logging.getLogger("BookmarkOrganizer")
        self.logger.setLevel(logging.DEBUG)

        # File handler - always log to file
        try:
            file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_format = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_format)
            self.logger.addHandler(file_handler)
        except Exception:
            pass  # Fail silently if log file can't be written

        # Console handler - only in debug mode
        self.console_handler = None
        if os.environ.get('BOOKMARK_DEBUG', '').lower() in ('1', 'true', 'yes'):
            self.enable_console()

    def enable_console(self):
        """Enable console logging."""
        if self.console_handler is None:
            self.console_handler = logging.StreamHandler(sys.stdout)
            self.console_handler.setLevel(logging.INFO)
            console_format = logging.Formatter('%(levelname)s: %(message)s')
            self.console_handler.setFormatter(console_format)
            self.logger.addHandler(self.console_handler)

    def disable_console(self):
        """Disable console logging."""
        if self.console_handler:
            self.logger.removeHandler(self.console_handler)
            self.console_handler = None

    def debug(self, msg, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        self.logger.exception(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self.logger.critical(msg, *args, **kwargs)


# Module-level logger instance
log = AppLogger()
