"""Persistent local-state services used by the desktop shell."""

from __future__ import annotations

import hashlib
import hmac
import json
import platform
import re
import secrets
import sys
import threading
import zipfile
from dataclasses import dataclass
from datetime import datetime
from importlib import metadata, util
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from urllib.parse import unquote, urlsplit

from bookmark_organizer_pro.constants import (
    APP_NAME,
    APP_VERSION,
    DATA_DIR,
    LOG_FILE,
    MASTER_BOOKMARKS_FILE,
    SETTINGS_FILE,
    SUPPORT_BUNDLES_DIR,
)
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.utils import clamp, safe_int
from bookmark_organizer_pro.utils.runtime import atomic_json_write as _atomic_json_write

if TYPE_CHECKING:
    from bookmark_organizer_pro.managers import BookmarkManager


_DEPENDENCY_MODULES = {
    "Pillow": ("Pillow", "PIL"),
    "darkdetect": ("darkdetect", "darkdetect"),
    "sv-ttk": ("sv-ttk", "sv_ttk"),
    "FastEmbed": ("fastembed", "fastembed"),
    "LanceDB": ("lancedb", "lancedb"),
    "FastMCP": ("fastmcp", "fastmcp"),
    "OpenAI": ("openai", "openai"),
}

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
    r"\s+\|\s+(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)"
    r"\s+\|\s+(?P<logger>[A-Za-z0-9_.-]{1,80})\s+\|\s*(?P<message>.*)$",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://[^\s<>'\"\])}]+", re.IGNORECASE)
_EXCEPTION_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_.]{0,79}(?:Error|Exception))\b"
)
_SAFE_EXCEPTION_TYPES = {
    "ConnectionError",
    "Exception",
    "FileNotFoundError",
    "HTTPError",
    "IOError",
    "JSONDecodeError",
    "OSError",
    "PermissionError",
    "RuntimeError",
    "TclError",
    "TimeoutError",
    "TypeError",
    "ValueError",
}
_SAFE_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_SUPPORT_FILE_NAMES = (
    "diagnostics.json",
    "diagnostics.txt",
    "recent_log_redacted.txt",
    "crash_reports_redacted.txt",
    "README.txt",
)


def _pseudonym(kind: str, value: str, key: bytes) -> str:
    digest = hmac.new(key, value.encode("utf-8", errors="replace"), hashlib.sha256)
    return f"[{kind}:{digest.hexdigest()[:12]}]"


def _safe_url_label(
    raw_url: str,
    *,
    retain_url_hosts: bool,
    key: bytes,
) -> str:
    try:
        parsed = urlsplit(raw_url)
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower()
    except Exception:
        host = ""
    if retain_url_hosts and host:
        return f"[URL_HOST:{host}]"
    return _pseudonym("URL", raw_url, key)


def redact_text(
    text: str,
    *,
    retain_url_hosts: bool = False,
    pseudonym_key: bytes | None = None,
) -> str:
    """Pseudonymize diagnostic text without retaining content-bearing values."""
    if not text:
        return ""
    key = pseudonym_key or secrets.token_bytes(32)
    redacted = unquote(str(text))
    redacted = re.sub(
        r"\\u([0-9a-fA-F]{4})",
        lambda match: chr(int(match.group(1), 16)),
        redacted,
    )
    redacted = _URL_RE.sub(
        lambda match: _safe_url_label(
            match.group(0),
            retain_url_hosts=retain_url_hosts,
            key=key,
        ),
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b[A-Z]:\\Users\\[^\\\r\n]+(?:\\[^\s\r\n|]*)?",
        lambda match: _pseudonym("LOCAL_PATH", match.group(0), key),
        redacted,
    )
    redacted = re.sub(
        r"(?i)(?:/home/|/Users/)[^/\s\r\n]+(?:/[^\s\r\n|]*)?",
        lambda match: _pseudonym("LOCAL_PATH", match.group(0), key),
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        lambda match: _pseudonym("EMAIL", match.group(0), key),
        redacted,
    )
    redacted = re.sub(
        r"""(?ix)
        (
            ["']?(?:title|bookmark[_-]?title|content|snippet|page[_-]?text|username)
            ["']?\s*[:=]\s*
        )
        (?:
            ["']([^"'\r\n]{1,4096})["']
            |
            ([^\r\n,}]{1,4096})
        )
        """,
        lambda match: (
            f"{match.group(1)}"
            f"{_pseudonym('CONTENT', (match.group(2) or match.group(3) or '').strip(), key)}"
        ),
        redacted,
    )
    redacted = re.sub(
        r"(?i)(Bearer\s+)[A-Za-z0-9._~+/\-=]+",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)(Authorization\s*[:=]\s*)[^\r\n]+",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"""(?ix)
        (
            (?:api[_-]?key|apiToken|access[_-]?token|refresh[_-]?token|
               token|secret|password|passwd|cookie|session)
            \s*["']?\s*[:=]\s*["']?\s*
        )
        [^"'\s,}]+
        """,
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)((?:api[_-]?key|token|secret|password)=)[^&\s]+",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?<![A-Za-z0-9])[A-Za-z0-9+/]{20,}={0,2}(?![A-Za-z0-9])",
        "[ENCODED_VALUE]",
        redacted,
    )
    return redacted


def _file_metadata(path: Path) -> Dict[str, Any]:
    try:
        stat = path.stat()
        return {
            "exists": True,
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        }
    except OSError:
        return {"exists": False, "size_bytes": 0, "modified": ""}


def _dependency_status() -> Dict[str, Dict[str, Any]]:
    status: Dict[str, Dict[str, Any]] = {}
    for label, (distribution, module_name) in _DEPENDENCY_MODULES.items():
        available = util.find_spec(module_name) is not None
        version = ""
        if available:
            try:
                version = metadata.version(distribution)
            except metadata.PackageNotFoundError:
                version = "available"
        status[label] = {"available": available, "version": version}
    return status


def _sanitize_log_line(
    line: str,
    *,
    retain_url_hosts: bool,
    pseudonym_key: bytes,
) -> str:
    """Keep operational log shape while replacing all free-form detail."""
    decoded = unquote(str(line or ""))
    match = _LOG_LINE_RE.match(decoded)
    if match:
        timestamp = match.group("timestamp")
        level = match.group("level").upper()
        if level not in _SAFE_LOG_LEVELS:
            level = "INFO"
        logger_name = (
            "BookmarkOrganizer"
            if match.group("logger") == "BookmarkOrganizer"
            else "application"
        )
        message = match.group("message")
        parts = [
            timestamp,
            level,
            logger_name,
            f"detail={_pseudonym('REDACTED', message, pseudonym_key)}",
        ]
    else:
        marker = "TRACEBACK" if decoded.lstrip().startswith("Traceback") else "DETAIL"
        parts = [
            marker,
            f"detail={_pseudonym('REDACTED', decoded, pseudonym_key)}",
        ]
        message = decoded

    exception_types = sorted(
        name for name in set(_EXCEPTION_RE.findall(message))
        if name in _SAFE_EXCEPTION_TYPES
    )[:3]
    if exception_types:
        parts.append(f"exception_type={','.join(exception_types)}")
    if retain_url_hosts:
        hosts = []
        for raw_url in _URL_RE.findall(message):
            try:
                host = (urlsplit(raw_url).hostname or "").encode("idna").decode("ascii")
            except Exception:
                host = ""
            host = host.lower()
            if host and host not in hosts:
                hosts.append(host)
        if hosts:
            parts.append(f"url_hosts={','.join(hosts[:5])}")
    return " | ".join(parts)


def _recent_log_lines(
    limit: int = 250,
    *,
    retain_url_hosts: bool = False,
    pseudonym_key: bytes | None = None,
) -> List[str]:
    key = pseudonym_key or secrets.token_bytes(32)
    if not LOG_FILE.exists():
        return []
    try:
        raw_lines = LOG_FILE.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()[-max(0, min(int(limit), 1000)):]
        return [
            _sanitize_log_line(
                line,
                retain_url_hosts=retain_url_hosts,
                pseudonym_key=key,
            )
            for line in raw_lines
        ]
    except (OSError, TypeError, ValueError):
        return ["ERROR | detail=[LOG_READ_ERROR]"]


def _allowlisted_job_health(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {"available": False}
    result: Dict[str, Any] = {"available": True}
    integer_keys = (
        "jobs",
        "running",
        "failures",
        "retryable_failures",
        "average_duration_ms",
        "processed_bytes",
        "storage_growth_7d_bytes",
        "ledger_bytes",
    )
    for key in integer_keys:
        try:
            result[key] = max(0, int(raw.get(key, 0)))
        except (TypeError, ValueError):
            result[key] = 0
    try:
        result["failure_rate"] = min(1.0, max(0.0, float(raw.get("failure_rate", 0.0))))
    except (TypeError, ValueError):
        result["failure_rate"] = 0.0
    result["privacy"] = {
        "content_stored": False,
        "urls_stored": False,
        "telemetry": False,
    }
    return result


def build_diagnostics_snapshot(
    *,
    retain_url_hosts: bool = False,
    pseudonym_key: bytes | None = None,
    _recent_log: List[str] | None = None,
) -> Dict[str, Any]:
    """Build a redacted diagnostics snapshot without bookmark contents."""
    key = pseudonym_key or secrets.token_bytes(32)
    recent_log = (
        list(_recent_log)
        if _recent_log is not None
        else _recent_log_lines(
            retain_url_hosts=retain_url_hosts,
            pseudonym_key=key,
        )
    )
    recent_errors = [
        line for line in recent_log
        if any(marker in line.upper() for marker in ("ERROR", "CRITICAL", "TRACEBACK", "EXCEPTION"))
    ][-50:]

    try:
        from bookmark_organizer_pro.services.job_ledger import JobLedger
        job_health = _allowlisted_job_health(JobLedger().health())
    except Exception:
        log.debug("Could not summarize job ledger", exc_info=True)
        job_health = {"available": False}

    try:
        from bookmark_organizer_pro.services.processing_timeline import ProcessingTimelineService

        processing_health = ProcessingTimelineService().diagnostics()
    except Exception:
        log.debug("Could not summarize processing timeline", exc_info=True)
        processing_health = {"available": False}

    try:
        from bookmark_organizer_pro.services.mcp_auth import MCPTokenManager
        credential_health = MCPTokenManager().diagnostics()
    except Exception:
        log.debug("Could not summarize credential inventory", exc_info=True)
        credential_health = {"available": False, "recovery_required": False}

    return {
        "schema": "bookmark-organizer-pro/support-diagnostics",
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "application": {
            "name": APP_NAME,
            "version": APP_VERSION,
            "python": sys.version.split()[0],
            "platform": f"{platform.system()} {platform.release()}",
            "architecture": platform.machine(),
        },
        "dependencies": _dependency_status(),
        "data_files": {
            "bookmarks": _file_metadata(MASTER_BOOKMARKS_FILE),
            "settings": _file_metadata(SETTINGS_FILE),
            "log": _file_metadata(LOG_FILE),
        },
        "recent_errors": recent_errors,
        "job_health": job_health,
        "processing_health": processing_health,
        "credential_health": credential_health,
        "privacy": {
            "bookmark_contents_included": False,
            "free_form_log_messages_included": False,
            "secrets_redacted": True,
            "url_hosts_included": bool(retain_url_hosts),
            "recent_log_lines": len(recent_log),
        },
    }


def format_diagnostics(snapshot: Dict[str, Any] | None = None) -> str:
    """Return a clipboard-friendly diagnostics summary."""
    snapshot = snapshot or build_diagnostics_snapshot()
    app = snapshot["application"]
    lines = [
        f"{app['name']} v{app['version']}",
        f"Generated: {snapshot['generated_at']}",
        f"Python: {app['python']}",
        f"Platform: {app['platform']} ({app['architecture']})",
        "",
        "Optional Dependencies:",
    ]
    for name, info in snapshot["dependencies"].items():
        version = f" {info['version']}" if info.get("version") else ""
        lines.append(f"- {name}: {'available' if info['available'] else 'missing'}{version}")

    lines.extend(["", "Data Files:"])
    for name, info in snapshot["data_files"].items():
        state = "present" if info["exists"] else "missing"
        lines.append(f"- {name}: {state}, {info['size_bytes']} bytes, modified {info['modified'] or 'n/a'}")

    lines.append("")
    lines.append(f"Recent Errors: {len(snapshot['recent_errors'])}")
    for line in snapshot["recent_errors"][-8:]:
        lines.append(f"- {line}")
    jobs = snapshot.get("job_health", {})
    if jobs.get("jobs") is not None:
        lines.extend([
            "",
            "Local Job Health:",
            f"- Completed: {jobs['jobs']}",
            f"- Failures: {jobs['failures']} ({jobs['failure_rate']:.1%})",
            f"- Retryable: {jobs['retryable_failures']}",
            f"- Processed storage (7d): {jobs['storage_growth_7d_bytes']} bytes",
        ])
    processing = snapshot.get("processing_health", {})
    if processing.get("available"):
        lines.extend([
            "",
            "Processing Timeline:",
            f"- Job events: {processing.get('job_events', 0)}",
            f"- Snapshot failures: {processing.get('snapshot_failures', 0)}",
            f"- Snapshot versions: {processing.get('snapshot_versions', 0)}",
            f"- Retryable failures: {processing.get('retryable_failures', 0)}",
        ])
    credentials = snapshot.get("credential_health", {})
    if credentials.get("credential_count") is not None:
        lines.extend([
            "",
            "Local Credential Health:",
            f"- Active: {credentials['active']}",
            f"- Expired: {credentials['expired']}",
            f"- Revoked: {credentials['revoked']}",
            f"- Successful uses: {credentials['successful_uses']}",
            f"- Denied uses: {credentials['failed_uses']}",
        ])
    lines.append("")
    privacy = snapshot.get("privacy", {})
    host_state = "included by user choice" if privacy.get("url_hosts_included") else "excluded"
    lines.append(
        "Privacy: bookmark contents excluded; free-form log messages excluded; "
        f"secrets redacted; URL hosts {host_state}."
    )
    return "\n".join(lines)


@dataclass(frozen=True)
class SupportBundlePreview:
    """Immutable text payload shown before the exact same files are saved."""

    generated_at: str
    files: Tuple[Tuple[str, str], ...]
    retain_url_hosts: bool = False

    def as_dict(self) -> Dict[str, str]:
        return dict(self.files)

    def render(self) -> str:
        sections = []
        for name, content in self.files:
            sections.append(f"===== {name} =====\n{content}")
        return "\n\n".join(sections)


def _safe_report_name(path: Path) -> str:
    """A crash filename fit to print in a bundle.

    The reader finds these by glob, so the name is as untrusted as the body:
    anything can create a file called crash-<anything>.log in that folder.
    """
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", path.name)
    return stem[:80] if stem else "crash-report"


def _redacted_crash_reports(
    limit: int = 3,
    *,
    retain_url_hosts: bool = False,
    pseudonym_key: bytes | None = None,
) -> str:
    """The newest crash reports, whole and redacted.

    The log is sampled to its last few hundred lines, so a crash that happened
    before a busy stretch rotates out of the bundle exactly when it matters
    most. Crash reports are separate files and are included in full.
    """
    from bookmark_organizer_pro.logging_config import (
        is_crash_header_line,
        latest_crash_reports,
    )

    key = pseudonym_key or secrets.token_bytes(32)
    sections: List[str] = []
    for path in latest_crash_reports(limit, directory=Path(LOG_FILE).parent):
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            sections.append(f"=== {_safe_report_name(path)} ===" + "\n" + "ERROR | detail=[CRASH_READ_ERROR]")
            continue
        # The header is fields the crash writer produced itself (build,
        # interpreter, origin, thread) and holds no user content, so it passes
        # through. It ends at the first blank line; everything after that is a
        # traceback and gets the same treatment as a log line. The block is
        # closed on the first non-header line as well, so an exception message
        # containing a newline cannot pose as a header and slip through.
        lines: List[str] = []
        in_header = True
        for line in raw.splitlines():
            if in_header and is_crash_header_line(line):
                lines.append(line)
                continue
            in_header = False
            lines.append(
                _sanitize_log_line(
                    line, retain_url_hosts=retain_url_hosts, pseudonym_key=key,
                )
            )
        redacted = "\n".join(lines)
        sections.append(f"=== {_safe_report_name(path)} ===" + "\n" + redacted)
    return "\n\n".join(sections)


def build_support_bundle_preview(
    *,
    retain_url_hosts: bool = False,
) -> SupportBundlePreview:
    """Build the complete allowlisted bundle payload without writing a file."""
    pseudonym_key = secrets.token_bytes(32)
    recent_log_lines = _recent_log_lines(
        retain_url_hosts=retain_url_hosts,
        pseudonym_key=pseudonym_key,
    )
    snapshot = build_diagnostics_snapshot(
        retain_url_hosts=retain_url_hosts,
        pseudonym_key=pseudonym_key,
        _recent_log=recent_log_lines,
    )
    recent_log = "\n".join(recent_log_lines)
    readme = (
        "Content-private support bundle.\n\n"
        "This archive contains only allowlisted runtime metadata and keyed event "
        "fingerprints. It excludes bookmark titles/content, free-form log messages, "
        "URL paths/queries/fragments, usernames, local paths, credentials, and "
        "settings values. URL hosts are "
        f"{'included by explicit preview choice' if retain_url_hosts else 'excluded'}.\n"
    )
    files = (
        ("diagnostics.json", json.dumps(snapshot, indent=2, sort_keys=True)),
        ("diagnostics.txt", format_diagnostics(snapshot)),
        (
            "recent_log_redacted.txt",
            recent_log or "No log file was available.",
        ),
        (
            "crash_reports_redacted.txt",
            _redacted_crash_reports(
                retain_url_hosts=retain_url_hosts, pseudonym_key=pseudonym_key,
            ) or "No crash reports were recorded.",
        ),
        ("README.txt", readme),
    )
    if tuple(name for name, _content in files) != _SUPPORT_FILE_NAMES:
        raise RuntimeError("Support bundle file allowlist drifted")
    return SupportBundlePreview(
        generated_at=snapshot["generated_at"],
        files=files,
        retain_url_hosts=bool(retain_url_hosts),
    )


def export_redacted_support_bundle(
    destination: str | Path | None = None,
    *,
    preview: SupportBundlePreview | None = None,
) -> Path:
    """Write the exact content-private files previously exposed by a preview."""
    payload = preview or build_support_bundle_preview()
    names = tuple(name for name, _content in payload.files)
    if names != _SUPPORT_FILE_NAMES:
        raise ValueError("Support bundle preview contains files outside the allowlist")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if destination is None:
        SUPPORT_BUNDLES_DIR.mkdir(parents=True, exist_ok=True)
        bundle_path = SUPPORT_BUNDLES_DIR / f"support_bundle_{timestamp}.zip"
    else:
        target = Path(destination).expanduser()
        if target.suffix.lower() == ".zip":
            target.parent.mkdir(parents=True, exist_ok=True)
            bundle_path = target
        else:
            target.mkdir(parents=True, exist_ok=True)
            bundle_path = target / f"support_bundle_{timestamp}.zip"

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in payload.files:
            bundle.writestr(name, content)
    return bundle_path


# =============================================================================
# Scheduled Backups
# =============================================================================
class BackupScheduler:
    """Schedule automatic backups"""
    
    BACKUP_DIR = DATA_DIR / "backups"
    CONFIG_FILE = DATA_DIR / "backup_config.json"
    
    def __init__(self, bookmark_manager: BookmarkManager):
        self.bookmark_manager = bookmark_manager
        self.config = self._load_config()
        self._timer: Optional[threading.Timer] = None
        self._running = False
        
        self.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    def _load_config(self) -> Dict:
        """Load backup configuration"""
        default = {
            "enabled": False,
            "interval_hours": 24,
            "max_backups": 10,
            "last_backup": None,
            "backup_location": str(self.BACKUP_DIR)
        }
        
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    default.update(loaded)
            except Exception as e:
                log.warning(f"Could not load backup config: {e}")

        default["enabled"] = bool(default.get("enabled", False))
        default["interval_hours"] = clamp(safe_int(default.get("interval_hours"), 24), 1, 24 * 30)
        default["max_backups"] = clamp(safe_int(default.get("max_backups"), 10), 1, 100)
        backup_location = str(default.get("backup_location") or self.BACKUP_DIR)
        default["backup_location"] = backup_location

        return default
    
    def _save_config(self):
        """Save backup configuration"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _atomic_json_write(self.CONFIG_FILE, self.config)
    
    def start(self):
        """Start the backup scheduler"""
        if not self.config["enabled"]:
            return
        
        self._running = True
        self._schedule_next()
    
    def stop(self):
        """Stop the backup scheduler"""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
    
    def _schedule_next(self):
        """Schedule the next backup"""
        if not self._running:
            return
        
        interval_seconds = self.config["interval_hours"] * 3600
        self._timer = threading.Timer(interval_seconds, self._do_backup)
        self._timer.daemon = True
        self._timer.start()
    
    def _do_backup(self):
        """Perform a backup"""
        try:
            self.create_backup()
            self.config["last_backup"] = datetime.now().isoformat()
            self._save_config()
            self._cleanup_old_backups()
        except Exception as e:
            log.warning(f"Backup failed: {e}")
        
        # Schedule next
        if self._running:
            self._schedule_next()
    
    def create_backup(self, location: str = None) -> str:
        """Create a backup now"""
        backup_dir = Path(location or self.config.get("backup_location") or self.BACKUP_DIR)
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"bookmark_backup_{timestamp}.json"
        filepath = backup_dir / filename
        
        # Export to JSON
        self.bookmark_manager.export_json(str(filepath))
        
        return str(filepath)
    
    def _cleanup_old_backups(self):
        """Remove old backups beyond max_backups limit"""
        backup_dir = Path(self.config.get("backup_location") or self.BACKUP_DIR)
        backup_stats = []
        for backup_file in backup_dir.glob("bookmark_backup_*.json"):
            try:
                backup_stats.append((backup_file, backup_file.stat().st_mtime))
            except OSError as e:
                log.warning(f"Could not inspect backup {backup_file}: {e}")
        backups = [file for file, _ in sorted(backup_stats, key=lambda item: item[1], reverse=True)]
        
        for old_backup in backups[self.config["max_backups"]:]:
            try:
                old_backup.unlink()
            except OSError as e:
                log.warning(f"Could not remove old backup {old_backup}: {e}")
    
    def get_backups(self) -> List[Dict]:
        """Get list of available backups"""
        backups = []
        
        backup_dir = Path(self.config.get("backup_location") or self.BACKUP_DIR)
        for backup_file in backup_dir.glob("bookmark_backup_*.json"):
            try:
                stat = backup_file.stat()
                backups.append({
                    "filename": backup_file.name,
                    "path": str(backup_file),
                    "size": stat.st_size,
                    "date": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
            except OSError as e:
                log.warning(f"Could not inspect backup {backup_file}: {e}")
        
        return sorted(backups, key=lambda x: x['date'], reverse=True)
    
    def restore_backup(self, filepath: str) -> Tuple[int, int]:
        """Restore from a backup file"""
        return self.bookmark_manager.import_json_file(filepath)
    
    def set_enabled(self, enabled: bool):
        """Enable or disable scheduled backups"""
        self.config["enabled"] = enabled
        self._save_config()
        
        if enabled:
            self.start()
        else:
            self.stop()
    
    def set_interval(self, hours: int):
        """Set backup interval in hours"""
        self.config["interval_hours"] = clamp(safe_int(hours, 24), 1, 24 * 30)
        self._save_config()
        
        # Restart scheduler with new interval
        if self._running:
            self.stop()
            self.start()


# =============================================================================
# Version History
# =============================================================================
class VersionHistory:
    """Track bookmark changes and allow restoration"""
    
    HISTORY_FILE = DATA_DIR / "version_history.json"
    MAX_VERSIONS = 50
    
    def __init__(self):
        self.versions: List[Dict] = []
        self._load_history()
    
    def _load_history(self):
        """Load version history"""
        if self.HISTORY_FILE.exists():
            try:
                with open(self.HISTORY_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.versions = [entry for entry in data if isinstance(entry, dict)][-self.MAX_VERSIONS:]
            except Exception as e:
                log.warning(f"Could not load version history: {e}")
                self.versions = []
    
    def _save_history(self):
        """Save version history"""
        self.HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.versions = self.versions[-self.MAX_VERSIONS:]
        _atomic_json_write(self.HISTORY_FILE, self.versions)
    
    def record_change(self, action: str, bookmark_id: int, 
                      old_data: Dict = None, new_data: Dict = None):
        """Record a change to the history"""
        version = {
            "timestamp": datetime.now().isoformat(),
            "action": action,  # "add", "edit", "delete", "move", "bulk"
            "bookmark_id": safe_int(bookmark_id, 0),
            "old_data": old_data if isinstance(old_data, dict) else None,
            "new_data": new_data if isinstance(new_data, dict) else None,
        }
        
        self.versions.append(version)
        self._save_history()
    
    def record_bulk_change(self, action: str, bookmark_ids: List[int],
                           description: str):
        """Record a bulk change"""
        normalized_ids = []
        for bookmark_id in bookmark_ids or []:
            value = safe_int(bookmark_id, 0)
            if value:
                normalized_ids.append(value)
        version = {
            "timestamp": datetime.now().isoformat(),
            "action": f"bulk_{action}",
            "bookmark_ids": normalized_ids,
            "description": description
        }
        
        self.versions.append(version)
        self._save_history()
    
    def get_history(self, limit: int = 20) -> List[Dict]:
        """Get recent history entries"""
        limit = clamp(safe_int(limit, 20), 1, self.MAX_VERSIONS)
        return list(reversed(self.versions[-limit:]))
    
    def get_bookmark_history(self, bookmark_id: int) -> List[Dict]:
        """Get history for a specific bookmark"""
        bookmark_id = safe_int(bookmark_id, 0)
        if not bookmark_id:
            return []
        return [
            v for v in self.versions 
            if v.get("bookmark_id") == bookmark_id or 
               bookmark_id in (v.get("bookmark_ids") or [])
        ]
    
    def clear_history(self):
        """Clear all history"""
        self.versions = []
        self._save_history()




# =============================================================================
# Per-Category Colors
# =============================================================================
class CategoryColorManager:
    """Persists per-category color assignments to a local JSON file."""
    
    COLORS_FILE = DATA_DIR / "category_colors.json"
    
    DEFAULT_COLORS = [
        "#58a6ff", "#3fb950", "#f0883e", "#a371f7", "#f778ba",
        "#79c0ff", "#7ee787", "#ffa657", "#d2a8ff", "#ff7b72",
        "#56d4dd", "#e3b341", "#8b949e", "#6e7681", "#238636"
    ]
    
    def __init__(self):
        self.colors: Dict[str, str] = {}
        self._load_colors()
    
    def _load_colors(self):
        """Load custom colors from file"""
        if self.COLORS_FILE.exists():
            try:
                with open(self.COLORS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.colors = {
                        str(category): str(color)
                        for category, color in data.items()
                        if self._is_hex_color(str(color))
                    }
            except Exception as e:
                log.warning(f"Could not load category colors: {e}")
    
    def _save_colors(self):
        """Save colors to file"""
        self.COLORS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _atomic_json_write(self.COLORS_FILE, self.colors)

    @staticmethod
    def _is_hex_color(color: str) -> bool:
        return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", str(color or "").strip()))
    
    def get_color(self, category: str) -> str:
        """Get color for a category"""
        category = str(category or "")
        if category in self.colors:
            return self.colors[category]
        
        # Generate consistent color from category name
        hash_val = sum(ord(c) for c in category)
        return self.DEFAULT_COLORS[hash_val % len(self.DEFAULT_COLORS)]
    
    def set_color(self, category: str, color: str):
        """Set custom color for a category"""
        category = str(category or "").strip()
        color = str(color or "").strip()
        if not category or not self._is_hex_color(color):
            return
        self.colors[category] = color
        self._save_colors()
    
    def reset_color(self, category: str):
        """Reset category to default color"""
        if category in self.colors:
            del self.colors[category]
            self._save_colors()
    
    def get_all_colors(self) -> Dict[str, str]:
        """Get all category colors"""
        return self.colors.copy()


# =============================================================================
# Custom Fonts Manager
# =============================================================================
class FontManager:
    """Manage custom fonts for the application"""
    
    FONTS_FILE = DATA_DIR / "font_settings.json"
    
    # Common safe fonts
    AVAILABLE_FONTS = {
        "ui": [
            "Segoe UI", "SF Pro Display", "Helvetica Neue", "Arial",
            "Roboto", "Open Sans", "Lato", "Inter", "Noto Sans"
        ],
        "mono": [
            "Consolas", "SF Mono", "Monaco", "Menlo", "Fira Code",
            "JetBrains Mono", "Source Code Pro", "Cascadia Code",
            "Ubuntu Mono", "Courier New"
        ]
    }
    
    def __init__(self):
        self.settings = self._load_settings()
    
    def _load_settings(self) -> Dict:
        """Load font settings"""
        default = {
            "ui_font": "Segoe UI",
            "mono_font": "Consolas",
            "ui_size": 10,
            "mono_size": 10
        }
        
        if self.FONTS_FILE.exists():
            try:
                with open(self.FONTS_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    default.update(loaded)
            except Exception as e:
                log.warning(f"Could not load font settings: {e}")

        default["ui_font"] = str(default.get("ui_font") or "Segoe UI")[:80]
        default["mono_font"] = str(default.get("mono_font") or "Consolas")[:80]
        default["ui_size"] = clamp(safe_int(default.get("ui_size"), 10), 6, 32)
        default["mono_size"] = clamp(safe_int(default.get("mono_size"), 10), 6, 32)
        
        return default
    
    def _save_settings(self):
        """Save font settings"""
        self.FONTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _atomic_json_write(self.FONTS_FILE, self.settings)
    
    def get_ui_font(self) -> Tuple[str, int]:
        """Get UI font tuple"""
        return (self.settings["ui_font"], self.settings["ui_size"])
    
    def get_mono_font(self) -> Tuple[str, int]:
        """Get monospace font tuple"""
        return (self.settings["mono_font"], self.settings["mono_size"])
    
    def set_ui_font(self, family: str, size: int = None):
        """Set UI font"""
        self.settings["ui_font"] = str(family or "Segoe UI")[:80]
        if size is not None:
            self.settings["ui_size"] = clamp(safe_int(size, self.settings["ui_size"]), 6, 32)
        self._save_settings()
    
    def set_mono_font(self, family: str, size: int = None):
        """Set monospace font"""
        self.settings["mono_font"] = str(family or "Consolas")[:80]
        if size is not None:
            self.settings["mono_size"] = clamp(safe_int(size, self.settings["mono_size"]), 6, 32)
        self._save_settings()
    
    def get_available_fonts(self) -> List[str]:
        """Get list of available system fonts"""
        try:
            import tkinter.font as tkfont
            return list(tkfont.families())
        except Exception:
            return self.AVAILABLE_FONTS["ui"] + self.AVAILABLE_FONTS["mono"]
