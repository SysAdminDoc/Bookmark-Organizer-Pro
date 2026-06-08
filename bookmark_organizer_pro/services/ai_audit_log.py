"""Structured AI audit log for bookmark modifications.

Every AI action on a bookmark is recorded as a JSON line in
~/.bookmark_organizer/logs/ai_audit.jsonl

Each entry captures: what changed, what the AI suggested, what was applied,
the provider/model used, and the bookmark before/after state. This log is
designed to be machine-readable so a coding agent can review it and extract
patterns for improving the categorization engine.

Format per line (JSONL):
{
  "timestamp": "2026-06-05T18:30:00",
  "action": "categorize|tag|title|summarize|enrich",
  "provider": "ollama",
  "model": "qwen3.5",
  "bookmark_id": 12345,
  "url": "https://example.com",
  "before": { "category": "Uncategorized", "title": "...", "tags": [...] },
  "after":  { "category": "Technology", "title": "...", "tags": [...] },
  "ai_response": { "category": "Technology", "confidence": 0.92, "tags": [...], "summary": "..." },
  "applied": true,
  "reason": "confidence 0.92 >= threshold 0.5"
}
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from bookmark_organizer_pro.constants import LOGS_DIR
from bookmark_organizer_pro.logging_config import log

AI_AUDIT_FILE = LOGS_DIR / "ai_audit.jsonl"
_write_lock = threading.Lock()


def _ensure_log_dir():
    AI_AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)


def log_ai_action(
    action: str,
    provider: str,
    model: str,
    bookmark_id: int,
    url: str,
    before: Dict[str, Any],
    after: Dict[str, Any],
    ai_response: Dict[str, Any],
    applied: bool = True,
    reason: str = "",
):
    """Write one structured AI audit entry."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "provider": provider,
        "model": model,
        "bookmark_id": bookmark_id,
        "url": url[:500],
        "before": before,
        "after": after,
        "ai_response": ai_response,
        "applied": applied,
        "reason": reason,
    }

    try:
        _ensure_log_dir()
        line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
        with _write_lock:
            with open(AI_AUDIT_FILE, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception as exc:
        log.warning(f"Failed to write AI audit log: {exc}")


def log_categorize(
    provider: str, model: str, bookmark_id: int, url: str,
    old_category: str, new_category: str,
    confidence: float, ai_tags: List[str],
    suggested_title: str = "", summary: str = "",
    applied: bool = True, reason: str = "",
    old_title: str = "", old_tags: Optional[List[str]] = None,
):
    """Log an AI categorization action."""
    from urllib.parse import urlparse
    domain = ""
    try:
        domain = urlparse(url).netloc.lower()
    except Exception:
        pass
    before: Dict[str, Any] = {"category": old_category}
    if old_title:
        before["title"] = old_title[:200]
    if old_tags:
        before["tags"] = old_tags
    if domain:
        before["domain"] = domain
    log_ai_action(
        action="categorize",
        provider=provider, model=model,
        bookmark_id=bookmark_id, url=url,
        before=before,
        after={"category": new_category},
        ai_response={
            "category": new_category,
            "confidence": confidence,
            "tags": ai_tags,
            "suggested_title": suggested_title,
            "summary": summary,
        },
        applied=applied, reason=reason,
    )


def log_tag_suggestion(
    provider: str, model: str, bookmark_id: int, url: str,
    old_tags: List[str], new_tags: List[str], ai_tags: List[str],
    applied: bool = True,
):
    """Log AI tag suggestions."""
    log_ai_action(
        action="tag",
        provider=provider, model=model,
        bookmark_id=bookmark_id, url=url,
        before={"tags": old_tags},
        after={"tags": new_tags},
        ai_response={"suggested_tags": ai_tags},
        applied=applied,
    )


def log_title_improvement(
    provider: str, model: str, bookmark_id: int, url: str,
    old_title: str, new_title: str,
    applied: bool = True,
):
    """Log AI title improvement."""
    log_ai_action(
        action="title",
        provider=provider, model=model,
        bookmark_id=bookmark_id, url=url,
        before={"title": old_title},
        after={"title": new_title},
        ai_response={"suggested_title": new_title},
        applied=applied,
    )


def log_summary(
    provider: str, model: str, bookmark_id: int, url: str,
    summary: str, applied: bool = True,
):
    """Log AI summary generation."""
    log_ai_action(
        action="summarize",
        provider=provider, model=model,
        bookmark_id=bookmark_id, url=url,
        before={}, after={"description": summary[:200]},
        ai_response={"summary": summary},
        applied=applied,
    )


def log_batch_result(
    provider: str, model: str, bookmark_id: int, url: str,
    old_category: str, old_tags: List[str], old_title: str,
    result: Dict[str, Any], applied: bool = True, reason: str = "",
):
    """Log a batch AI processing result (categorize + tags + summary in one call)."""
    log_ai_action(
        action="enrich",
        provider=provider, model=model,
        bookmark_id=bookmark_id, url=url,
        before={"category": old_category, "tags": old_tags, "title": old_title},
        after={
            "category": result.get("category", old_category),
            "tags": result.get("tags", old_tags),
            "summary": (result.get("summary") or "")[:200],
        },
        ai_response=result,
        applied=applied, reason=reason,
    )


def read_audit_log(limit: int = 1000) -> List[Dict]:
    """Read the most recent audit log entries."""
    if not AI_AUDIT_FILE.exists():
        return []
    entries = []
    try:
        with open(AI_AUDIT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return []
    return entries[-limit:]


def get_audit_stats() -> Dict[str, Any]:
    """Get summary statistics from the audit log."""
    entries = read_audit_log(limit=100000)
    if not entries:
        return {"total": 0}

    actions = {}
    providers = {}
    categories_changed = {}

    for e in entries:
        action = e.get("action", "unknown")
        actions[action] = actions.get(action, 0) + 1
        prov = e.get("provider", "unknown")
        providers[prov] = providers.get(prov, 0) + 1

        if action == "categorize" and e.get("applied"):
            new_cat = e.get("after", {}).get("category", "")
            if new_cat:
                categories_changed[new_cat] = categories_changed.get(new_cat, 0) + 1

    return {
        "total": len(entries),
        "by_action": actions,
        "by_provider": providers,
        "top_categories": dict(sorted(categories_changed.items(), key=lambda x: -x[1])[:20]),
        "first": entries[0].get("timestamp", "") if entries else "",
        "last": entries[-1].get("timestamp", "") if entries else "",
    }
