"""Persistent JSON storage with atomic writes, backups, and corruption recovery."""

import json
import os
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from ..constants import BACKUP_DIR
from ..logging_config import log
from ..models import Bookmark


class StorageManager:
    """Atomic JSON persistence with timestamped backups.

    - save() writes to a temp file then atomically replaces the target
    - Each save creates a timestamped backup; only the 10 most recent are kept
    - load() tolerates individual corrupt entries (logs warning, skips)
    """

    CURRENT_VERSION = 4

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self._lock = threading.Lock()

    def save(self, data: List[Dict], metadata: Dict = None):
        """Save data atomically."""
        payload = {
            "version": self.CURRENT_VERSION,
            "metadata": metadata or {
                "saved_at": datetime.now().isoformat(),
                "count": len(data),
            },
            "data": data,
        }

        with self._lock:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)

            if self.filepath.exists():
                self._create_backup()

            fd, temp_path = tempfile.mkstemp(
                dir=self.filepath.parent, suffix='.tmp', text=True
            )
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)

                os.replace(temp_path, self.filepath)
            except Exception:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise

    def _create_backup(self):
        """Create a timestamped backup; rotate to keep only 10."""
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_name = f"{self.filepath.stem}_{timestamp}.json"
            backup_path = BACKUP_DIR / backup_name
            counter = 1
            while backup_path.exists():
                backup_path = BACKUP_DIR / f"{self.filepath.stem}_{timestamp}_{counter}.json"
                counter += 1
            shutil.copy2(self.filepath, backup_path)

            backups = sorted(BACKUP_DIR.glob(f"{self.filepath.stem}_*.json"))
            while len(backups) > 10:
                try:
                    backups.pop(0).unlink()
                except OSError:
                    break
        except Exception as e:
            log.warning(f"Backup creation failed: {e}")

    def load(self) -> List[Bookmark]:
        """Load bookmarks, skipping individual corrupt entries."""
        if not self.filepath.exists():
            return []

        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                raw = json.load(f)

            if isinstance(raw, list):
                items = raw
            elif isinstance(raw, dict):
                items = raw.get("data", [])
            else:
                log.warning(f"Unexpected data format in {self.filepath}")
                return []
            if not isinstance(items, list):
                log.warning(f"Unexpected bookmark data shape in {self.filepath}")
                return []

            bookmarks = []
            for item in items:
                if not isinstance(item, dict):
                    log.warning("Skipping non-object bookmark entry")
                    continue
                try:
                    bookmarks.append(Bookmark.from_dict(item))
                except Exception as e:
                    log.warning(f"Skipping corrupt bookmark entry: {e}")
            return bookmarks
        except json.JSONDecodeError as e:
            log.error(f"Corrupt JSON in {self.filepath}: {e}")
            return []
        except Exception as e:
            log.error(f"Could not load data from {self.filepath}: {e}")
            return []

    def get_backups(self) -> List[Tuple[str, datetime, int]]:
        """List available backups as (filename, mtime, size) tuples."""
        backups = []
        for f in BACKUP_DIR.glob(f"{self.filepath.stem}_*.json"):
            try:
                stat = f.stat()
                backups.append((
                    f.name,
                    datetime.fromtimestamp(stat.st_mtime),
                    stat.st_size,
                ))
            except Exception as e:
                log.warning(f"Error reading backup {f.name}: {e}")
        return sorted(backups, key=lambda x: x[1], reverse=True)

    def restore_backup(self, backup_name: str) -> bool:
        """Restore from a named backup file."""
        backup_root = BACKUP_DIR.resolve()
        backup_path = (backup_root / backup_name).resolve()
        try:
            backup_path.relative_to(backup_root)
        except ValueError:
            log.error(f"Invalid backup name (path traversal blocked): {backup_name}")
            return False
        if not backup_path.is_file():
            log.error(f"Backup not found: {backup_name}")
            return False
        try:
            with self._lock:
                self.filepath.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_path, self.filepath)
            return True
        except Exception as e:
            log.error(f"Failed to restore backup {backup_name}: {e}")
            return False
