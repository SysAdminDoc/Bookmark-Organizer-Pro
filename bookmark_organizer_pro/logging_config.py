"""Centralized logging system for the application.

Provides structured logging to both file and optional console output.
Singleton pattern ensures consistent logging throughout the application.
Set BOOKMARK_DEBUG=1 environment variable to enable console logging.
"""

import faulthandler
import logging
import logging.handlers
import os
import platform
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

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

        # File handler with rotation — 5 MB max, 3 backups
        self._file_handler = None
        self._fallback_handler = None
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding='utf-8',
            )
            file_handler.setLevel(logging.DEBUG)
            file_format = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_format)
            self.logger.addHandler(file_handler)
            self._file_handler = file_handler
        except Exception:
            self._fallback_handler = logging.StreamHandler(sys.stderr)
            self._fallback_handler.setLevel(logging.WARNING)
            self._fallback_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
            self.logger.addHandler(self._fallback_handler)

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


# ── Crash capture ────────────────────────────────────────────────────────────
#
# Startup is guarded, but once Tk's mainloop is pumping an unhandled exception
# goes to Tk's default handler, which prints to a stderr a windowed or frozen
# build discards. Worker threads were guarded inconsistently. A crash therefore
# left nothing a user could send and nothing a maintainer could read.

CRASH_FILE_PREFIX = "crash-"
CRASH_FILE_SUFFIX = ".log"
_FAULT_HANDLER_STREAM = None


def crash_reports_dir() -> Path:
    """Where crash files live. Beside the log, but never rotated with it."""
    return Path(LOG_FILE).parent


def latest_crash_reports(limit: int = 5, *, directory: Path | None = None) -> list[Path]:
    """The newest crash files, newest first.

    ``directory`` lets a caller that already knows where the log lives look
    beside that log rather than beside this module's own ``LOG_FILE``; the two
    are the same path in a running app but diverge under test patching.
    """
    directory = Path(directory) if directory is not None else crash_reports_dir()
    if not directory.is_dir():
        return []
    reports = [
        path for path in directory.glob(f"{CRASH_FILE_PREFIX}*{CRASH_FILE_SUFFIX}")
        if path.is_file()
    ]
    reports.sort(key=lambda path: path.name, reverse=True)
    return reports[: max(0, int(limit))]


# Header fields this module writes itself. Every value is a build or runtime
# fact with no user content in it, so a support bundle may carry them verbatim
# while the traceback body below still goes through the log redactor.
CRASH_HEADER_KEYS = ("app", "when", "origin", "thread", "python", "platform", "frozen")


def is_crash_header_line(line: str) -> bool:
    """True for a header line this module wrote, which needs no redaction."""
    key, separator, _rest = line.partition(": ")
    return bool(separator) and key in CRASH_HEADER_KEYS


def format_crash_report(
    exc_type, exc_value, exc_traceback, *, origin: str, thread_name: str
) -> str:
    """The text written for one crash: what failed, where, and on what build."""
    from .constants import APP_NAME, APP_VERSION

    header = [
        f"app: {APP_NAME} {APP_VERSION}",
        f"when: {datetime.now().isoformat(timespec='seconds')}",
        f"origin: {origin}",
        f"thread: {thread_name}",
        # The interpreter path is deliberately omitted: it carries the user's
        # name on Windows and the header travels into support bundles verbatim.
        f"python: {sys.version.split()[0]} {platform.python_implementation()}",
        f"platform: {sys.platform}",
        f"frozen: {bool(getattr(sys, 'frozen', False) or hasattr(sys, '_MEIPASS'))}",
        "",
    ]
    body = "".join(
        traceback.format_exception(exc_type, exc_value, exc_traceback)
    ) or f"{exc_type}: {exc_value}\n"
    return "\n".join(header) + body


def write_crash_report(
    exc_type, exc_value, exc_traceback, *, origin: str, thread_name: str
) -> Path | None:
    """Write one crash file and return its path, or None if it cannot be written."""
    report = format_crash_report(
        exc_type, exc_value, exc_traceback, origin=origin, thread_name=thread_name
    )
    directory = crash_reports_dir()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = directory / f"{CRASH_FILE_PREFIX}{stamp}-{os.getpid()}{CRASH_FILE_SUFFIX}"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        # A second crash in the same second must not overwrite the first.
        counter = 1
        while target.exists():
            target = (
                directory
                / f"{CRASH_FILE_PREFIX}{stamp}-{os.getpid()}-{counter}{CRASH_FILE_SUFFIX}"
            )
            counter += 1
        target.write_text(report, encoding="utf-8")
    except OSError:
        return None
    return target


def install_crash_handlers(notify=None) -> None:
    """Route every unhandled failure to one crash file.

    ``notify`` is called with the crash file path so a desktop surface can offer
    to open it. It must not block; anything it raises is swallowed, because a
    failure while reporting a failure must not replace the original.
    """
    global _FAULT_HANDLER_STREAM

    def _handle(exc_type, exc_value, exc_traceback, *, origin: str, thread_name: str) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            return
        path = write_crash_report(
            exc_type, exc_value, exc_traceback, origin=origin, thread_name=thread_name
        )
        try:
            log.critical(
                f"Unhandled {exc_type.__name__} in {origin} "
                f"({thread_name}); report: {path or 'not written'}"
            )
        except Exception:
            pass
        if notify is not None and path is not None:
            try:
                notify(path)
            except Exception:
                pass

    def _sys_hook(exc_type, exc_value, exc_traceback):
        _handle(
            exc_type, exc_value, exc_traceback,
            origin="main", thread_name=threading.current_thread().name,
        )

    def _thread_hook(args):
        _handle(
            args.exc_type, args.exc_value, args.exc_traceback,
            origin="thread",
            thread_name=getattr(args.thread, "name", "unknown"),
        )

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook

    if _FAULT_HANDLER_STREAM is None:
        # A hard interpreter fault never reaches an excepthook, so it gets its
        # own always-open file rather than nothing at all.
        try:
            crash_reports_dir().mkdir(parents=True, exist_ok=True)
            _FAULT_HANDLER_STREAM = open(
                crash_reports_dir() / "faulthandler.log", "a", encoding="utf-8"
            )
            faulthandler.enable(file=_FAULT_HANDLER_STREAM)
        except (OSError, ValueError, RuntimeError):
            _FAULT_HANDLER_STREAM = None


def tk_exception_reporter(notify=None):
    """A ``Tk.report_callback_exception`` that records instead of printing.

    Tk's default handler writes to stderr and continues, which is invisible in a
    windowed or frozen build. This keeps the continue-running behaviour and adds
    the record.
    """

    def report(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            return
        path = write_crash_report(
            exc_type, exc_value, exc_traceback,
            origin="tk-callback", thread_name=threading.current_thread().name,
        )
        try:
            log.critical(
                f"Unhandled {exc_type.__name__} in a Tk callback; "
                f"report: {path or 'not written'}"
            )
        except Exception:
            pass
        if notify is not None and path is not None:
            try:
                notify(path)
            except Exception:
                pass

    return report
