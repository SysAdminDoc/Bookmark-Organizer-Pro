"""MCP auth token management with per-tool scope control.

Tokens can be read-only (query tools only) or read-write (all tools including
mutations like add_bookmark, create_flow, export_to_obsidian).
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
import threading
from pathlib import Path
from typing import Dict, Optional, Set

from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.logging_config import log

MCP_TOKENS_FILE = DATA_DIR / "mcp_tokens.json"

READ_ONLY_TOOLS = {
    "list_bookmarks", "get_bookmark", "search_bookmarks",
    "semantic_search", "hybrid_search", "list_tags", "list_categories",
    "get_extracted_text", "daily_digest", "list_dead_links",
    "list_flows", "get_flow", "list_snapshots",
}

WRITE_TOOLS = {
    "add_bookmark", "create_flow", "append_to_flow",
    "export_zip", "export_to_obsidian",
    "chat_with_collection", "summarize_bookmark",
}


class MCPTokenManager:
    """Manage MCP auth tokens with read-only vs. read-write scopes."""

    def __init__(self, filepath: Path = MCP_TOKENS_FILE):
        self.filepath = filepath
        self._tokens: Dict[str, dict] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        if not self.filepath.exists():
            return
        try:
            data = json.loads(self.filepath.read_text(encoding="utf-8"))
            self._tokens = data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            self._tokens = {}

    def _save(self):
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.filepath.parent, suffix=".tmp", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._tokens, f, indent=2)
            os.replace(tmp, self.filepath)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    def create_token(self, name: str, scope: str = "read-write") -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._tokens[token] = {
                "name": name,
                "scope": scope if scope in ("read-only", "read-write") else "read-write",
                "created_at": __import__("datetime").datetime.now().isoformat(),
            }
            self._save()
        log.info(f"MCP token created: {name} (scope={scope})")
        return token

    def revoke_token(self, token: str) -> bool:
        with self._lock:
            if token in self._tokens:
                name = self._tokens[token].get("name", "")
                del self._tokens[token]
                self._save()
                log.info(f"MCP token revoked: {name}")
                return True
        return False

    def list_tokens(self) -> list:
        with self._lock:
            return [
                {"token_prefix": t[:8] + "...", "name": v["name"],
                 "scope": v["scope"], "created_at": v.get("created_at", "")}
                for t, v in self._tokens.items()
            ]

    def validate(self, token: str, tool_name: str) -> bool:
        with self._lock:
            if token not in self._tokens:
                return False
            info = self._tokens[token]
            scope = info.get("scope", "read-write")
        if scope == "read-write":
            return True
        if scope == "read-only":
            return tool_name in READ_ONLY_TOOLS
        return False

    def get_scope(self, token: str) -> Optional[str]:
        with self._lock:
            info = self._tokens.get(token)
            return info["scope"] if info else None
