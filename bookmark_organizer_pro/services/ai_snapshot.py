"""Pre-operation snapshots for bulk AI actions.

Captures bookmark state (category, tags, title) before batch AI
operations so they can be selectively rolled back. Snapshots
auto-expire after 7 days.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.logging_config import log

AI_SNAPSHOTS_DIR = DATA_DIR / "ai_snapshots"
EXPIRY_DAYS = 7


def _ensure_dir():
    AI_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def create_snapshot(operation: str, bookmarks) -> str:
    """Snapshot category/tags/title for each bookmark before an AI batch.

    Returns the snapshot ID (ISO timestamp slug).
    """
    _ensure_dir()
    _expire_old()

    snap_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    records = []
    for bm in bookmarks:
        records.append({
            "id": bm.id,
            "category": bm.category,
            "parent_category": bm.parent_category,
            "tags": list(bm.tags),
            "ai_tags": list(bm.ai_tags),
            "title": bm.title,
        })

    data = {
        "snapshot_id": snap_id,
        "operation": operation,
        "created_at": datetime.now().isoformat(),
        "bookmark_count": len(records),
        "bookmarks": records,
    }

    path = AI_SNAPSHOTS_DIR / f"{snap_id}.json"
    fd, tmp = tempfile.mkstemp(dir=AI_SNAPSHOTS_DIR, suffix=".tmp", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise

    log.info(f"AI snapshot created: {snap_id} ({len(records)} bookmarks, op={operation})")
    return snap_id


def list_snapshots() -> List[Dict]:
    """List available AI operation snapshots (newest first)."""
    _ensure_dir()
    results = []
    for path in sorted(AI_SNAPSHOTS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            results.append({
                "snapshot_id": data.get("snapshot_id", path.stem),
                "operation": data.get("operation", ""),
                "created_at": data.get("created_at", ""),
                "bookmark_count": data.get("bookmark_count", 0),
            })
        except (OSError, json.JSONDecodeError):
            continue
    return results


def load_snapshot(snap_id: str) -> Optional[Dict]:
    """Load a snapshot by ID."""
    path = AI_SNAPSHOTS_DIR / f"{snap_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def restore_snapshot(snap_id: str, bookmark_manager) -> int:
    """Restore bookmarks to their pre-AI-operation state.

    Returns the number of bookmarks restored.
    """
    data = load_snapshot(snap_id)
    if not data:
        return 0

    restored = 0
    for record in data.get("bookmarks", []):
        bm = bookmark_manager.get_bookmark(record["id"])
        if not bm:
            continue
        bm.category = record["category"]
        bm.parent_category = record["parent_category"]
        bm.tags = list(record.get("tags", []))
        bm.ai_tags = list(record.get("ai_tags", []))
        bm.title = record["title"]
        restored += 1

    if restored:
        bookmark_manager.save_bookmarks()
    log.info(f"AI snapshot restored: {snap_id} ({restored} bookmarks)")
    return restored


def delete_snapshot(snap_id: str) -> bool:
    """Delete a snapshot file."""
    path = AI_SNAPSHOTS_DIR / f"{snap_id}.json"
    try:
        if path.exists():
            path.unlink()
            return True
    except OSError:
        pass
    return False


def _expire_old():
    """Remove snapshots older than EXPIRY_DAYS."""
    cutoff = datetime.now() - timedelta(days=EXPIRY_DAYS)
    for path in AI_SNAPSHOTS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            created = datetime.fromisoformat(data.get("created_at", ""))
            if created < cutoff:
                path.unlink()
                log.debug(f"Expired AI snapshot: {path.name}")
        except Exception:
            continue
