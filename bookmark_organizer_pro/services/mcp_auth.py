"""Named, scoped bearer credentials for MCP and the local REST API.

Only salted verifiers are persisted. Raw bearer secrets are returned once when
created or rotated and are intentionally unrecoverable afterward.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional

from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.services.atomic_document_store import (
    AtomicDocumentRecoveryError,
    AtomicDocumentStore,
)
from bookmark_organizer_pro.services.private_files import restrict_private_file

MCP_TOKENS_FILE = DATA_DIR / "mcp_tokens.json"
TOKEN_SALT_BYTES = 16
CREDENTIAL_SCHEMA_VERSION = 2
MAX_AUDIT_EVENTS = 500
FINGERPRINT_HEX_CHARS = 12

MCP_READ_SCOPE = "mcp:read"
MCP_WRITE_SCOPE = "mcp:write"
REST_READ_SCOPE = "rest:read"
REST_WRITE_SCOPE = "rest:write"
REST_EXTENSION_SCOPE = "rest:extension"

AUDIENCE_SCOPES = {
    "mcp": {MCP_READ_SCOPE, MCP_WRITE_SCOPE},
    "rest": {REST_READ_SCOPE, REST_WRITE_SCOPE, REST_EXTENSION_SCOPE},
}
ALL_SCOPES = frozenset().union(*AUDIENCE_SCOPES.values())

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
    "youtube_transcript",
    "chat_with_collection", "chat_with_collection_stream", "summarize_bookmark",
    "update_reader_highlight_note", "relink_reader_highlight", "record_reader_review",
}

_OPERATION_RE = re.compile(r"[^A-Za-z0-9:_./ -]+")


def _token_verifier(token: str, salt: bytes) -> str:
    """Return the salted verifier for a high-entropy bearer token."""
    return hashlib.sha256(salt + token.encode("utf-8")).hexdigest()


def _token_fingerprint(token: str) -> str:
    """Return a display-safe, truncated SHA-256 fingerprint."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:FINGERPRINT_HEX_CHARS]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_timestamp(value: object) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_operation(value: object) -> str:
    cleaned = _OPERATION_RE.sub("", str(value or "").strip())
    return cleaned[:80] or "unspecified"


@dataclass(frozen=True)
class CreatedCredential:
    """One-time credential creation/rotation result."""

    identifier: str
    token: str
    fingerprint: str


@dataclass(frozen=True)
class CredentialAuthResult:
    """Authorization decision without exposing bearer material."""

    allowed: bool
    reason: str
    credential_id: str = ""
    name: str = ""
    audience: str = ""
    scopes: tuple[str, ...] = ()


class MCPTokenManager:
    """Manage named local credentials across MCP and REST audiences.

    The historical class name remains as a compatibility surface for callers,
    while schema v2 stores audience-specific least-privilege scopes and audit
    metadata for both local protocols.
    """

    def __init__(self, filepath: Path = MCP_TOKENS_FILE):
        self.filepath = Path(filepath)
        self._tokens: Dict[str, dict] = {}
        self._document = self._empty_document()
        self._lock = threading.RLock()
        self._recovery_required = False
        self._using_legacy_fallback = False
        self._store = AtomicDocumentStore(
            self.filepath,
            schema="mcp-token-verifiers",
            current_version=CREDENTIAL_SCHEMA_VERSION,
            default_factory=self._empty_document,
            migrations={
                0: self._migrate_legacy,
                1: self._migrate_v1,
            },
            validator=self._validate_document,
            sensitive=True,
        )
        self._load()

    @staticmethod
    def _empty_document() -> dict:
        return {
            "credentials": {},
            "audit": [],
            "policy": {
                "ever_configured": False,
                "invalid_attempts": 0,
            },
        }

    @staticmethod
    def _legacy_record(
        token: str,
        info: dict,
        *,
        record_id: str | None = None,
    ) -> tuple[str, dict]:
        salt = secrets.token_bytes(TOKEN_SALT_BYTES)
        identifier = record_id or secrets.token_hex(8)
        scope = info.get("scope", "read-write")
        return identifier, {
            "name": str(info.get("name", "")),
            "scope": scope if scope in ("read-only", "read-write") else "read-only",
            "created_at": str(info.get("created_at", "")),
            "salt": salt.hex(),
            "verifier": _token_verifier(token, salt),
        }

    @staticmethod
    def _scope_label(scopes: Iterable[str], audience: str) -> str:
        scope_set = set(scopes)
        if audience == "mcp":
            return (
                "read-write"
                if MCP_WRITE_SCOPE in scope_set
                else "read-only"
            )
        if audience == "rest":
            if REST_EXTENSION_SCOPE in scope_set:
                return "browser-extension"
            return (
                "read-write"
                if REST_WRITE_SCOPE in scope_set
                else "read-only"
            )
        return "none"

    @classmethod
    def _migrate_legacy(cls, data: object) -> dict:
        """Convert raw-token-keyed legacy JSON into schema-v1 verifiers."""
        if not isinstance(data, dict):
            raise ValueError("MCP token document must be an object")
        migrated: Dict[str, dict] = {}
        for raw_token, info in data.items():
            if not isinstance(raw_token, str) or not raw_token or not isinstance(info, dict):
                continue
            identifier, record = cls._legacy_record(raw_token, info)
            migrated[identifier] = record
        return migrated

    @classmethod
    def _migrate_v1(cls, data: object) -> dict:
        """Add explicit audience/scopes without expanding legacy privileges."""
        if not isinstance(data, dict):
            raise ValueError("MCP verifier document must be an object")
        credentials: Dict[str, dict] = {}
        for identifier, old in data.items():
            if not isinstance(identifier, str) or not isinstance(old, dict):
                continue
            legacy_scope = old.get("scope", "read-only")
            scopes = (
                [MCP_READ_SCOPE, MCP_WRITE_SCOPE]
                if legacy_scope == "read-write"
                else [MCP_READ_SCOPE]
            )
            credentials[identifier] = {
                "name": str(old.get("name", ""))[:120],
                "audience": "mcp",
                "scopes": scopes,
                "created_at": str(old.get("created_at", "")),
                "last_used_at": "",
                "last_failed_at": "",
                "expires_at": "",
                "revoked_at": "",
                "rotated_at": "",
                "rotation_count": 0,
                "fingerprint": f"legacy-{identifier[:8]}",
                "salt": str(old.get("salt", "")),
                "verifier": str(old.get("verifier", "")),
                "successful_uses": 0,
                "failed_uses": 0,
                "migration_source": "mcp-v1",
            }
        return {
            "credentials": credentials,
            "audit": [],
            "policy": {
                "ever_configured": bool(credentials),
                "invalid_attempts": 0,
            },
        }

    @staticmethod
    def _valid_record(record: object) -> bool:
        if not isinstance(record, dict):
            return False
        try:
            salt = bytes.fromhex(str(record["salt"]))
            verifier = str(record["verifier"])
            audience = str(record["audience"])
            scopes = record["scopes"]
            fingerprint = str(record["fingerprint"])
        except (KeyError, TypeError, ValueError):
            return False
        if audience not in AUDIENCE_SCOPES:
            return False
        if (
            not isinstance(scopes, list)
            or not scopes
            or len(scopes) != len(set(scopes))
            or any(scope not in AUDIENCE_SCOPES[audience] for scope in scopes)
        ):
            return False
        if len(salt) != TOKEN_SALT_BYTES:
            return False
        if len(verifier) != hashlib.sha256().digest_size * 2:
            return False
        if not fingerprint or len(fingerprint) > 32:
            return False
        for key in (
            "name", "created_at", "last_used_at", "last_failed_at",
            "expires_at", "revoked_at", "rotated_at",
        ):
            if not isinstance(record.get(key), str):
                return False
        for key in ("rotation_count", "successful_uses", "failed_uses"):
            value = record.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return False
        return True

    @classmethod
    def _validate_document(cls, data: object) -> None:
        if not isinstance(data, dict):
            raise ValueError("Credential document must be an object")
        credentials = data.get("credentials")
        audit = data.get("audit")
        policy = data.get("policy")
        if not isinstance(credentials, dict):
            raise ValueError("Credential inventory must be an object")
        if any(
            not isinstance(identifier, str) or not cls._valid_record(record)
            for identifier, record in credentials.items()
        ):
            raise ValueError("Credential inventory contains an invalid record")
        if not isinstance(audit, list) or len(audit) > MAX_AUDIT_EVENTS:
            raise ValueError("Credential audit log is invalid")
        required_event_fields = {
            "timestamp", "credential_id", "name", "audience",
            "operation", "result", "reason",
        }
        if any(
            not isinstance(event, dict)
            or set(event) != required_event_fields
            or any(not isinstance(value, str) for value in event.values())
            for event in audit
        ):
            raise ValueError("Credential audit log contains an invalid event")
        if not isinstance(policy, dict):
            raise ValueError("Credential policy must be an object")
        if not isinstance(policy.get("ever_configured"), bool):
            raise ValueError("Credential policy is missing configuration state")
        invalid_attempts = policy.get("invalid_attempts")
        if (
            isinstance(invalid_attempts, bool)
            or not isinstance(invalid_attempts, int)
            or invalid_attempts < 0
        ):
            raise ValueError("Credential policy has an invalid attempt count")

    def _legacy_fallback(self) -> dict:
        """Keep legacy credentials usable if migration cannot be persisted."""
        if not self.filepath.exists():
            return self._empty_document()
        try:
            data = json.loads(self.filepath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._empty_document()
        if isinstance(data, dict) and data.get("schema") == "mcp-token-verifiers":
            return self._empty_document()
        try:
            return self._migrate_v1(self._migrate_legacy(data))
        except ValueError:
            return self._empty_document()

    def _sync_views(self, document: dict) -> None:
        self._document = document
        self._tokens = document.get("credentials", {})

    def _load(self) -> None:
        self._secure_persisted_files()
        legacy_fallback = self._legacy_fallback()
        document = self._store.load()
        self._recovery_required = self._store.status.recovery_required
        if self._recovery_required and legacy_fallback["credentials"]:
            document = legacy_fallback
            self._using_legacy_fallback = True
            log.warning("Credential migration is pending; legacy access remains usable")
        else:
            self._using_legacy_fallback = False
        self._sync_views(document)
        self._secure_persisted_files()

    def _secure_persisted_files(self) -> None:
        for path in (self.filepath, self._store.backup_path):
            if path.exists():
                restrict_private_file(path)

    def _reload(self) -> None:
        loaded = self._store.load()
        self._recovery_required = self._store.status.recovery_required
        if not self._recovery_required:
            self._using_legacy_fallback = False
            self._sync_views(loaded)

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = " ".join(str(name or "").split())
        if not normalized:
            raise ValueError("Credential name is required")
        if len(normalized) > 120:
            raise ValueError("Credential name must be 120 characters or fewer")
        return normalized

    @staticmethod
    def _normalize_scopes(audience: str, scopes: Iterable[str]) -> list[str]:
        if audience not in AUDIENCE_SCOPES:
            raise ValueError("Credential audience must be 'mcp' or 'rest'")
        normalized = sorted({str(scope) for scope in scopes})
        if not normalized:
            raise ValueError("At least one credential scope is required")
        if any(scope not in AUDIENCE_SCOPES[audience] for scope in normalized):
            raise ValueError(f"Credential scopes do not belong to the {audience} audience")
        return normalized

    @staticmethod
    def _normalize_expiry(
        expires_at: str | datetime | None,
        expires_in_seconds: int | None,
        *,
        now: Optional[datetime] = None,
    ) -> str:
        current = now or _utc_now()
        if expires_at is not None and expires_in_seconds is not None:
            raise ValueError("Specify expires_at or expires_in_seconds, not both")
        if expires_in_seconds is not None:
            if isinstance(expires_in_seconds, bool):
                raise ValueError("Credential lifetime must be an integer")
            try:
                seconds = int(expires_in_seconds)
            except (TypeError, ValueError) as exc:
                raise ValueError("Credential lifetime must be an integer") from exc
            if seconds <= 0:
                raise ValueError("Credential lifetime must be positive")
            return _isoformat(current + timedelta(seconds=seconds))
        if expires_at is None or str(expires_at).strip() == "":
            return ""
        parsed = (
            expires_at
            if isinstance(expires_at, datetime)
            else _parse_timestamp(expires_at)
        )
        if parsed is None:
            raise ValueError("Credential expiry must be an ISO-8601 timestamp")
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
        if parsed <= current:
            raise ValueError("Credential expiry must be in the future")
        return _isoformat(parsed)

    @classmethod
    def _new_record(
        cls,
        token: str,
        *,
        name: str,
        audience: str,
        scopes: Iterable[str],
        expires_at: str = "",
        migration_source: str = "",
    ) -> dict:
        salt = secrets.token_bytes(TOKEN_SALT_BYTES)
        return {
            "name": cls._normalize_name(name),
            "audience": audience,
            "scopes": cls._normalize_scopes(audience, scopes),
            "created_at": _isoformat(_utc_now()),
            "last_used_at": "",
            "last_failed_at": "",
            "expires_at": expires_at,
            "revoked_at": "",
            "rotated_at": "",
            "rotation_count": 0,
            "fingerprint": _token_fingerprint(token),
            "salt": salt.hex(),
            "verifier": _token_verifier(token, salt),
            "successful_uses": 0,
            "failed_uses": 0,
            "migration_source": migration_source,
        }

    @staticmethod
    def _append_audit(
        document: dict,
        *,
        credential_id: str,
        record: Optional[dict],
        audience: str,
        operation: str,
        result: str,
        reason: str,
        timestamp: Optional[str] = None,
    ) -> None:
        event = {
            "timestamp": timestamp or _isoformat(_utc_now()),
            "credential_id": credential_id,
            "name": str((record or {}).get("name", "")),
            "audience": str(audience or (record or {}).get("audience", "")),
            "operation": _safe_operation(operation),
            "result": "success" if result == "success" else "denied",
            "reason": str(reason)[:80],
        }
        audit = document.setdefault("audit", [])
        audit.append(event)
        if len(audit) > MAX_AUDIT_EVENTS:
            del audit[:-MAX_AUDIT_EVENTS]

    def create_credential(
        self,
        name: str,
        *,
        audience: str,
        scopes: Iterable[str],
        expires_at: str | datetime | None = None,
        expires_in_seconds: int | None = None,
    ) -> CreatedCredential:
        normalized_name = self._normalize_name(name)
        normalized_scopes = self._normalize_scopes(audience, scopes)
        expiry = self._normalize_expiry(expires_at, expires_in_seconds)
        token = secrets.token_urlsafe(32)
        identifier = secrets.token_hex(8)
        record = self._new_record(
            token,
            name=normalized_name,
            audience=audience,
            scopes=normalized_scopes,
            expires_at=expiry,
        )
        with self._lock:
            def add(document: dict) -> None:
                document["credentials"][identifier] = record
                document["policy"]["ever_configured"] = True
                self._append_audit(
                    document,
                    credential_id=identifier,
                    record=record,
                    audience=audience,
                    operation="credential:create",
                    result="success",
                    reason="created",
                )

            self._sync_views(self._store.update(add))
        log.info(
            "Local credential created: audience=%s scopes=%s fingerprint=%s",
            audience,
            ",".join(normalized_scopes),
            record["fingerprint"],
        )
        return CreatedCredential(identifier, token, record["fingerprint"])

    def create_token(
        self,
        name: str,
        scope: str = "read-only",
        *,
        expires_at: str | datetime | None = None,
        expires_in_seconds: int | None = None,
    ) -> str:
        """Compatibility helper for MCP read-only/read-write credentials."""
        if scope == "read-only":
            scopes = [MCP_READ_SCOPE]
        elif scope == "read-write":
            scopes = [MCP_READ_SCOPE, MCP_WRITE_SCOPE]
        else:
            raise ValueError("MCP scope must be 'read-only' or 'read-write'")
        return self.create_credential(
            name,
            audience="mcp",
            scopes=scopes,
            expires_at=expires_at,
            expires_in_seconds=expires_in_seconds,
        ).token

    def import_legacy_rest_token(self, token: str) -> Optional[str]:
        """Register the historical global REST token with unchanged privileges."""
        token = str(token or "").strip()
        if not token:
            return None
        fingerprint = _token_fingerprint(token)
        result: Dict[str, object] = {"identifier": "", "created": False}
        identifier = secrets.token_hex(8)
        record = self._new_record(
            token,
            name="Legacy local API",
            audience="rest",
            scopes=[
                REST_READ_SCOPE,
                REST_WRITE_SCOPE,
                REST_EXTENSION_SCOPE,
            ],
            migration_source="legacy-rest-token",
        )
        with self._lock:
            def add(document: dict) -> None:
                for existing_identifier, existing in document["credentials"].items():
                    if (
                        existing.get("audience") == "rest"
                        and existing.get("migration_source") == "legacy-rest-token"
                    ):
                        # Rotation/revocation in the credential inventory is
                        # authoritative. Never resurrect the historical source
                        # secret merely because it remains in keyring/fallback
                        # storage for backward compatibility.
                        result["identifier"] = existing_identifier
                        return
                existing_identifier, existing = self._match_in(
                    document["credentials"],
                    token,
                )
                if (
                    existing_identifier is not None
                    and existing is not None
                    and existing.get("audience") == "rest"
                ):
                    result["identifier"] = existing_identifier
                    return
                document["credentials"][identifier] = record
                document["policy"]["ever_configured"] = True
                result["identifier"] = identifier
                result["created"] = True
                self._append_audit(
                    document,
                    credential_id=identifier,
                    record=record,
                    audience="rest",
                    operation="credential:migrate",
                    result="success",
                    reason="legacy_privileges_preserved",
                )

            self._sync_views(self._store.update(add))
        if result["created"]:
            log.info(
                "Migrated legacy REST bearer token to credential inventory "
                "(fingerprint=%s)",
                fingerprint,
            )
        return str(result["identifier"])

    def _match_in(
        self,
        credentials: Dict[str, dict],
        token: str,
    ) -> tuple[Optional[str], Optional[dict]]:
        if not token:
            return None, None
        matched_identifier = None
        matched_record = None
        for identifier, record in credentials.items():
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

    @staticmethod
    def _record_status(record: dict, now: Optional[datetime] = None) -> str:
        if record.get("revoked_at"):
            return "revoked"
        expiry = _parse_timestamp(record.get("expires_at"))
        if expiry is not None and expiry <= (now or _utc_now()):
            return "expired"
        return "active"

    def authorize(
        self,
        token: str,
        required_scope: str,
        *,
        operation: str,
        audience: str,
    ) -> CredentialAuthResult:
        if required_scope not in ALL_SCOPES:
            raise ValueError("Unknown credential scope")
        if required_scope not in AUDIENCE_SCOPES.get(audience, set()):
            raise ValueError("Credential scope does not match its audience")
        with self._lock:
            # AtomicDocumentStore.update() reloads and validates the latest
            # document under its interprocess lock. Avoid a redundant normal
            # read on every request; only re-probe a known recovery state.
            if self._recovery_required:
                self._reload()
            if self._recovery_required and self._using_legacy_fallback:
                identifier, record = self._match_in(self._tokens, str(token or ""))
                if (
                    identifier is not None
                    and record is not None
                    and record.get("audience") == audience
                    and self._record_status(record) == "active"
                    and required_scope in record.get("scopes", [])
                ):
                    return CredentialAuthResult(
                        True,
                        "authorized_legacy_fallback",
                        identifier,
                        str(record.get("name") or ""),
                        audience,
                        tuple(record.get("scopes", [])),
                    )
                return CredentialAuthResult(False, "credential_store_recovery_required")
        decision: Dict[str, object] = {}
        now = _utc_now()
        timestamp = _isoformat(now)

        def inspect(document: dict) -> None:
            credentials = document["credentials"]
            identifier, record = self._match_in(credentials, str(token or ""))
            if identifier is None or record is None:
                document["policy"]["invalid_attempts"] += 1
                self._append_audit(
                    document,
                    credential_id="",
                    record=None,
                    audience=audience,
                    operation=operation,
                    result="denied",
                    reason="invalid_credential",
                    timestamp=timestamp,
                )
                decision.update(
                    allowed=False,
                    reason="invalid_credential",
                    credential_id="",
                    record=None,
                )
                return

            status = self._record_status(record, now)
            reason = ""
            if record.get("audience") != audience:
                reason = "wrong_audience"
            elif status == "revoked":
                reason = "credential_revoked"
            elif status == "expired":
                reason = "credential_expired"
            elif required_scope not in record.get("scopes", []):
                reason = "insufficient_scope"

            allowed = not reason
            if allowed:
                record["last_used_at"] = timestamp
                record["successful_uses"] += 1
                result = "success"
                reason = "authorized"
            else:
                record["last_failed_at"] = timestamp
                record["failed_uses"] += 1
                result = "denied"
            self._append_audit(
                document,
                credential_id=identifier,
                record=record,
                audience=audience,
                operation=operation,
                result=result,
                reason=reason,
                timestamp=timestamp,
            )
            decision.update(
                allowed=allowed,
                reason=reason,
                credential_id=identifier,
                record=dict(record),
            )

        with self._lock:
            try:
                self._sync_views(self._store.update(inspect))
            except (AtomicDocumentRecoveryError, OSError, ValueError) as exc:
                self._recovery_required = isinstance(exc, AtomicDocumentRecoveryError)
                log.error("Credential authorization could not be recorded: %s", type(exc).__name__)
                reason = (
                    "credential_store_recovery_required"
                    if self._recovery_required
                    else "credential_store_unavailable"
                )
                return CredentialAuthResult(False, reason)

        record = decision.get("record")
        record_dict = record if isinstance(record, dict) else {}
        return CredentialAuthResult(
            bool(decision.get("allowed")),
            str(decision.get("reason") or "invalid_credential"),
            str(decision.get("credential_id") or ""),
            str(record_dict.get("name") or ""),
            str(record_dict.get("audience") or audience),
            tuple(str(scope) for scope in record_dict.get("scopes", [])),
        )

    def validate(self, token: str, tool_name: str) -> bool:
        required_scope = (
            MCP_READ_SCOPE
            if tool_name in READ_ONLY_TOOLS
            else MCP_WRITE_SCOPE
        )
        return self.authorize(
            token,
            required_scope,
            operation=f"mcp:{_safe_operation(tool_name)}",
            audience="mcp",
        ).allowed

    def get_scope(self, token: str) -> Optional[str]:
        """Compatibility lookup without creating an audit event."""
        with self._lock:
            self._reload()
            _, record = self._match_in(self._tokens, str(token or ""))
            if (
                record is None
                or record.get("audience") != "mcp"
                or self._record_status(record) != "active"
            ):
                return None
            return self._scope_label(record.get("scopes", []), "mcp")

    def revoke_credential(self, identifier: str) -> bool:
        changed = {"value": False}
        with self._lock:
            def revoke(document: dict) -> None:
                record = document["credentials"].get(identifier)
                if record is None or record.get("revoked_at"):
                    return
                record["revoked_at"] = _isoformat(_utc_now())
                changed["value"] = True
                self._append_audit(
                    document,
                    credential_id=identifier,
                    record=record,
                    audience=record["audience"],
                    operation="credential:revoke",
                    result="success",
                    reason="revoked",
                )

            self._sync_views(self._store.update(revoke))
        if changed["value"]:
            log.info("Local credential revoked: id=%s", identifier[:8])
        return changed["value"]

    def revoke_token(self, token: str) -> bool:
        with self._lock:
            self._reload()
            identifier, _record = self._match_in(self._tokens, str(token or ""))
        return bool(identifier and self.revoke_credential(identifier))

    def rotate_credential(
        self,
        identifier: str,
        *,
        expires_at: str | datetime | None = None,
        expires_in_seconds: int | None = None,
    ) -> CreatedCredential:
        token = secrets.token_urlsafe(32)
        expiry_override = (
            expires_at is not None
            or expires_in_seconds is not None
        )
        normalized_expiry = (
            self._normalize_expiry(expires_at, expires_in_seconds)
            if expiry_override
            else ""
        )
        result: Dict[str, str] = {}
        with self._lock:
            def rotate(document: dict) -> None:
                record = document["credentials"].get(identifier)
                if record is None:
                    raise KeyError("Credential not found")
                if record.get("revoked_at"):
                    raise ValueError("Revoked credentials cannot be rotated")
                salt = secrets.token_bytes(TOKEN_SALT_BYTES)
                record["salt"] = salt.hex()
                record["verifier"] = _token_verifier(token, salt)
                record["fingerprint"] = _token_fingerprint(token)
                record["rotated_at"] = _isoformat(_utc_now())
                record["rotation_count"] += 1
                if expiry_override:
                    record["expires_at"] = normalized_expiry
                self._append_audit(
                    document,
                    credential_id=identifier,
                    record=record,
                    audience=record["audience"],
                    operation="credential:rotate",
                    result="success",
                    reason="rotated",
                )
                result["fingerprint"] = record["fingerprint"]

            self._sync_views(self._store.update(rotate))
        log.info("Local credential rotated: id=%s", identifier[:8])
        return CreatedCredential(identifier, token, result["fingerprint"])

    def list_credentials(
        self,
        *,
        audience: Optional[str] = None,
        include_revoked: bool = True,
    ) -> list[dict]:
        with self._lock:
            self._reload()
            if self._recovery_required:
                return [{
                    "id": "",
                    "name": "Recovery required",
                    "audience": audience or "",
                    "scopes": [],
                    "scope": "none",
                    "status": "recovery-required",
                    "created_at": "",
                    "last_used_at": "",
                    "last_failed_at": "",
                    "expires_at": "",
                    "revoked_at": "",
                    "rotated_at": "",
                    "rotation_count": 0,
                    "successful_uses": 0,
                    "failed_uses": 0,
                    "fingerprint": "unavailable",
                }]
            items = []
            for identifier, record in self._tokens.items():
                if audience is not None and record.get("audience") != audience:
                    continue
                status = self._record_status(record)
                if status == "revoked" and not include_revoked:
                    continue
                scopes = list(record.get("scopes", []))
                items.append({
                    "id": identifier,
                    "name": record.get("name", ""),
                    "audience": record.get("audience", ""),
                    "scopes": scopes,
                    "scope": self._scope_label(scopes, record.get("audience", "")),
                    "status": status,
                    "created_at": record.get("created_at", ""),
                    "last_used_at": record.get("last_used_at", ""),
                    "last_failed_at": record.get("last_failed_at", ""),
                    "expires_at": record.get("expires_at", ""),
                    "revoked_at": record.get("revoked_at", ""),
                    "rotated_at": record.get("rotated_at", ""),
                    "rotation_count": record.get("rotation_count", 0),
                    "successful_uses": record.get("successful_uses", 0),
                    "failed_uses": record.get("failed_uses", 0),
                    "fingerprint": record.get("fingerprint", ""),
                })
            return sorted(
                items,
                key=lambda item: (item["created_at"], item["id"]),
                reverse=True,
            )

    def list_tokens(self, audience: str = "mcp") -> list[dict]:
        """Compatibility inventory with no bearer-secret material."""
        return [
            {
                **item,
                "token_prefix": (
                    f"sha256:{item['fingerprint']}"
                    if item["fingerprint"] != "unavailable"
                    else "unavailable"
                ),
            }
            for item in self.list_credentials(audience=audience)
        ]

    def has_credentials(self, audience: Optional[str] = None) -> bool:
        """Return true after configuration, including revoked-only fail-closed state."""
        with self._lock:
            self._reload()
            if self._recovery_required:
                return True
            credentials = self._tokens.values()
            if audience is not None:
                credentials = (
                    record
                    for record in credentials
                    if record.get("audience") == audience
                )
            return any(True for _record in credentials)

    def list_audit(
        self,
        *,
        limit: int = 100,
        audience: Optional[str] = None,
    ) -> list[dict]:
        if isinstance(limit, bool):
            raise ValueError("Credential audit limit must be an integer")
        try:
            parsed_limit = int(limit)
        except (TypeError, ValueError) as exc:
            raise ValueError("Credential audit limit must be an integer") from exc
        bounded = max(1, min(parsed_limit, MAX_AUDIT_EVENTS))
        with self._lock:
            self._reload()
            events = self._document.get("audit", [])
            if audience is not None:
                events = [
                    event for event in events
                    if event.get("audience") == audience
                ]
            return [dict(event) for event in events[-bounded:]][::-1]

    def diagnostics(self) -> dict:
        """Return content-free aggregate state for support diagnostics."""
        credentials = self.list_credentials()
        if self._recovery_required:
            return {
                "available": False,
                "recovery_required": True,
                "credential_count": 0,
                "active": 0,
                "expired": 0,
                "revoked": 0,
                "mcp": 0,
                "rest": 0,
                "successful_uses": 0,
                "failed_uses": 0,
                "audit_events": 0,
            }
        return {
            "available": True,
            "recovery_required": False,
            "credential_count": len(credentials),
            "active": sum(item["status"] == "active" for item in credentials),
            "expired": sum(item["status"] == "expired" for item in credentials),
            "revoked": sum(item["status"] == "revoked" for item in credentials),
            "mcp": sum(item["audience"] == "mcp" for item in credentials),
            "rest": sum(item["audience"] == "rest" for item in credentials),
            "successful_uses": sum(item["successful_uses"] for item in credentials),
            "failed_uses": (
                sum(item["failed_uses"] for item in credentials)
                + int(self._document.get("policy", {}).get("invalid_attempts", 0))
            ),
            "audit_events": len(self._document.get("audit", [])),
        }
