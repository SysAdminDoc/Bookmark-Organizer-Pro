"""Persistent local-state services used by the desktop shell."""

from __future__ import annotations

import json
import platform
import re
import sys
import threading
import zipfile
from datetime import datetime
from importlib import metadata, util
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

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
    "pystray": ("pystray", "pystray"),
    "darkdetect": ("darkdetect", "darkdetect"),
    "sv-ttk": ("sv-ttk", "sv_ttk"),
    "FastEmbed": ("fastembed", "fastembed"),
    "LanceDB": ("lancedb", "lancedb"),
    "FastMCP": ("fastmcp", "fastmcp"),
    "OpenAI": ("openai", "openai"),
}


def redact_text(text: str) -> str:
    """Remove credentials and token-like values from diagnostic text."""
    if not text:
        return ""
    redacted = str(text)
    redacted = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/\-=]+", r"\1[REDACTED]", redacted)
    redacted = re.sub(r"(?i)(Authorization\s*[:=]\s*)[^\r\n]+", r"\1[REDACTED]", redacted)
    redacted = re.sub(
        r"(?i)((?:api[_-]?key|apiToken|token|secret|password)\s*[\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)((?:api[_-]?key|token|secret|password)=)[^&\s]+",
        r"\1[REDACTED]",
        redacted,
    )
    return redacted


def _file_metadata(path: Path) -> Dict[str, Any]:
    try:
        stat = path.stat()
        return {
            "name": path.name,
            "exists": True,
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        }
    except OSError:
        return {"name": path.name, "exists": False, "size_bytes": 0, "modified": ""}


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


def _recent_log_lines(limit: int = 250) -> List[str]:
    if not LOG_FILE.exists():
        return []
    try:
        return [redact_text(line) for line in LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]]
    except OSError as exc:
        return [f"Could not read log file: {exc}"]


def build_diagnostics_snapshot() -> Dict[str, Any]:
    """Build a redacted diagnostics snapshot without bookmark contents."""
    recent_log = _recent_log_lines()
    recent_errors = [
        line for line in recent_log
        if any(marker in line.upper() for marker in ("ERROR", "CRITICAL", "TRACEBACK", "EXCEPTION"))
    ][-50:]

    return {
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
        "privacy": {
            "bookmark_contents_included": False,
            "secrets_redacted": True,
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
    lines.append("")
    lines.append("Privacy: bookmark contents excluded; secrets redacted.")
    return "\n".join(lines)


def export_redacted_support_bundle(destination: str | Path | None = None) -> Path:
    """Write a support ZIP with diagnostics and redacted recent logs."""
    snapshot = build_diagnostics_snapshot()
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

    recent_log = "\n".join(_recent_log_lines())
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("diagnostics.json", json.dumps(snapshot, indent=2))
        bundle.writestr("diagnostics.txt", format_diagnostics(snapshot))
        bundle.writestr("recent_log_redacted.txt", recent_log or "No log file was available.")
        bundle.writestr(
            "README.txt",
            "Redacted support bundle. Bookmark contents, API keys, tokens, passwords, and secrets are excluded or redacted.\n",
        )
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
