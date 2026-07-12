"""MCP auth token management with per-tool scope control.

Only salted verifiers are persisted.  The bearer secret returned by
``create_token`` is intentionally unrecoverable after that call.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.services.atomic_document_store import AtomicDocumentStore

MCP_TOKENS_FILE = DATA_DIR / "mcp_tokens.json"
TOKEN_SALT_BYTES = 16

READ_ONLY_TOOLS = {
    "list_bookmarks", "get_bookmark", "search_bookmarks",
    "semantic_search", "hybrid_search", "list_tags", "list_categories",
    "get_extracted_text", "daily_digest", "list_dead_links",
    "list_flows", "get_flow", "list_snapshots",
    "list_reader_highlights", "list_due_reader_reviews", "export_reader_highlights",
}

WRITE_TOOLS = {
    "add_bookmark", "delete_bookmark", "update_bookmark",
    "toggle_pin", "mark_read_later", "add_tags", "remove_tags",
    "create_flow", "append_to_flow",
    "export_zip", "export_to_obsidian",
    "chat_with_collection", "chat_with_collection_stream", "summarize_bookmark",
    "update_reader_highlight_note", "record_reader_review",
}


def _token_verifier(token: str, salt: bytes) -> str:
    """Return the salted verifier for a high-entropy bearer token."""
    return hashlib.sha256(salt + token.encode("utf-8")).hexdigest()


class MCPTokenManager:
    """Manage MCP bearer verifiers with read-only vs. read-write scopes."""

    def __init__(self, filepath: Path = MCP_TOKENS_FILE):
        self.filepath = filepath
        self._tokens: Dict[str, dict] = {}
        self._lock = threading.RLock()
        self._recovery_required = False
        self._store = AtomicDocumentStore(
            filepath,
            schema="mcp-token-verifiers",
            current_version=1,
            migrations={0: self._migrate_legacy},
            validator=self._validate_records,
            sensitive=True,
        )
        self._load()

    @staticmethod
    def _record(token: str, info: dict, *, record_id: str | None = None) -> tuple[str, dict]:
        salt = secrets.token_bytes(TOKEN_SALT_BYTES)
        identifier = record_id or secrets.token_hex(8)
        scope = info.get("scope", "read-write")
        return identifier, {
            "name": str(info.get("name", "")),
            "scope": scope if scope in ("read-only", "read-write") else "read-write",
            "created_at": str(info.get("created_at", "")),
            "salt": salt.hex(),
            "verifier": _token_verifier(token, salt),
        }

    @staticmethod
    def _valid_record(record: object) -> bool:
        if not isinstance(record, dict):
            return False
        try:
            salt = bytes.fromhex(str(record["salt"]))
            verifier = str(record["verifier"])
        except (KeyError, TypeError, ValueError):
            return False
        return len(salt) == TOKEN_SALT_BYTES and len(verifier) == hashlib.sha256().digest_size * 2

    @classmethod
    def _migrate_legacy(cls, data: object) -> dict:
        """Convert the v1 raw-token-keyed document to verifier records."""
        if not isinstance(data, dict):
            raise ValueError("MCP token document must be an object")
        migrated: Dict[str, dict] = {}
        for raw_token, info in data.items():
            if not isinstance(raw_token, str) or not raw_token or not isinstance(info, dict):
                continue
            identifier, record = cls._record(raw_token, info)
            migrated[identifier] = record
        return migrated

    @classmethod
    def _validate_records(cls, data: object) -> None:
        if not isinstance(data, dict):
            raise ValueError("MCP verifier document must be an object")
        if any(not isinstance(identifier, str) or not cls._valid_record(record)
               for identifier, record in data.items()):
            raise ValueError("MCP verifier document contains an invalid record")

    def _legacy_fallback(self) -> dict:
        """Keep valid legacy credentials usable if their migration cannot persist."""
        if not self.filepath.exists():
            return {}
        try:
            data = json.loads(self.filepath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if isinstance(data, dict) and data.get("schema") == "mcp-token-verifiers":
            return {}
        try:
            return self._migrate_legacy(data)
        except ValueError:
            return {}

    def _load(self) -> None:
        legacy_fallback = self._legacy_fallback()
        self._tokens = self._store.load()
        self._recovery_required = self._store.status.recovery_required
        if self._recovery_required and legacy_fallback:
            self._tokens = legacy_fallback
            log.warning("MCP token migration is pending; legacy credentials remain usable")
        elif legacy_fallback:
            log.info("Migrated legacy MCP bearer tokens to salted verifier records")
        self._secure_persisted_files()

    @staticmethod
    def _restrict_windows_acl(path: Path) -> None:
        username = os.environ.get("USERNAME", "").strip()
        if not username:
            raise PermissionError("USERNAME is unavailable; cannot secure MCP token file")
        result = subprocess.run(
            [
                "icacls", str(path), "/inheritance:r",
                "/grant:r", f"{username}:(F)",
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise PermissionError("could not restrict MCP token file to the current user")

    def _secure_persisted_files(self) -> None:
        for path in (self.filepath, self._store.backup_path):
            if not path.exists():
                continue
            if os.name == "nt":
                self._restrict_windows_acl(path)
            else:
                os.chmod(path, 0o600)

    def _save(self) -> None:
        self._store.save(self._tokens)
        self._secure_persisted_files()

    def _reload(self) -> None:
        loaded = self._store.load()
        self._recovery_required = self._store.status.recovery_required
        if not self._recovery_required:
            self._tokens = loaded

    def create_token(self, name: str, scope: str = "read-write") -> str:
        token = secrets.token_urlsafe(32)
        identifier, record = self._record(
            token,
            {
                "name": name,
                "scope": scope,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        with self._lock:
            def add(document: dict) -> None:
                document[identifier] = record

            self._tokens = self._store.update(add)
            try:
                self._secure_persisted_files()
            except Exception:
                def rollback(document: dict) -> None:
                    document.pop(identifier, None)

                self._store.update(rollback)
                self._tokens.pop(identifier, None)
                raise
        log.info(f"MCP token created: {name} (scope={record['scope']})")
        return token

    def revoke_token(self, token: str) -> bool:
        with self._lock:
            self._reload()
            identifier, info = self._match(token)
            if identifier is not None and info is not None:
                name = info.get("name", "")
                def revoke(document: dict) -> None:
                    document.pop(identifier, None)

                self._tokens = self._store.update(revoke)
                self._secure_persisted_files()
                log.info(f"MCP token revoked: {name}")
                return True
        return False

    def list_tokens(self) -> list:
        with self._lock:
            self._reload()
            if self._recovery_required:
                return [{
                    "token_prefix": "unavailable",
                    "name": "Recovery required",
                    "scope": "none",
                    "created_at": "",
                }]
            return [
                {
                    "token_prefix": f"id:{identifier[:8]}",
                    "name": record.get("name", ""),
                    "scope": record.get("scope", "read-write"),
                    "created_at": record.get("created_at", ""),
                }
                for identifier, record in self._tokens.items()
            ]

    def _match(self, token: str) -> tuple[Optional[str], Optional[dict]]:
        """Find a verifier using constant-time comparisons without early exit."""
        if not token:
            return None, None
        matched_identifier = None
        matched_record = None
        for identifier, record in self._tokens.items():
            try:
                salt = bytes.fromhex(record["salt"])
                candidate = _token_verifier(token, salt)
                stored = str(record["verifier"])
            except (KeyError, TypeError, ValueError):
                candidate = hashlib.sha256(token.encode("utf-8")).hexdigest()
                stored = "0" * len(candidate)
            if secrets.compare_digest(stored, candidate):
                matched_identifier = identifier
                matched_record = record
        return matched_identifier, matched_record

    def validate(self, token: str, tool_name: str) -> bool:
        with self._lock:
            self._reload()
            _, info = self._match(token)
        if info is None:
            return False
        scope = info.get("scope", "read-write")
        if scope == "read-write":
            return True
        if scope == "read-only":
            return tool_name in READ_ONLY_TOOLS
        return False

    def get_scope(self, token: str) -> Optional[str]:
        with self._lock:
            self._reload()
            _, info = self._match(token)
            return info.get("scope") if info else None
