"""Revisioned, conflict-aware application settings persistence."""

from __future__ import annotations

import json
import math
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from bookmark_organizer_pro.constants import SETTINGS_FILE
from bookmark_organizer_pro.services.atomic_document_store import (
    AtomicDocumentConflictError,
    AtomicDocumentRecoveryError,
    AtomicDocumentStore,
)


SETTINGS_SCHEMA = "bookmark-organizer-pro/settings"
SETTINGS_SCHEMA_VERSION = 1
MAX_SETTINGS_BYTES = 2_000_000
MAX_SETTINGS_DEPTH = 12
MAX_SETTINGS_NODES = 20_000
MAX_SETTINGS_KEY_CHARS = 256
MAX_SETTINGS_STRING_CHARS = 500_000
DEFAULT_CONFLICT_RETRIES = 3


def _migrate_settings_v0(document: object) -> dict[str, Any]:
    """Wrap the historical plain JSON object without dropping unknown keys."""
    if not isinstance(document, dict):
        raise ValueError("legacy settings must be a JSON object")
    return deepcopy(document)


def _validate_settings(document: object) -> None:
    """Validate a bounded JSON object while allowing forward-compatible keys."""
    if not isinstance(document, dict):
        raise ValueError("settings document must be a JSON object")
    nodes = 0

    def visit(value: object, *, depth: int, path: str) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_SETTINGS_NODES:
            raise ValueError("settings document has too many values")
        if depth > MAX_SETTINGS_DEPTH:
            raise ValueError(f"settings value is nested too deeply at {path}")
        if value is None or isinstance(value, (bool, int)):
            return
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError(f"settings value must be finite at {path}")
            return
        if isinstance(value, str):
            if len(value) > MAX_SETTINGS_STRING_CHARS:
                raise ValueError(f"settings string is too long at {path}")
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, depth=depth + 1, path=f"{path}[{index}]")
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str) or not key or len(key) > MAX_SETTINGS_KEY_CHARS:
                    raise ValueError(f"settings key is invalid at {path}")
                visit(item, depth=depth + 1, path=f"{path}.{key}")
            return
        raise ValueError(f"settings value is not JSON-compatible at {path}")

    visit(document, depth=0, path="$")
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAX_SETTINGS_BYTES:
        raise ValueError("settings document exceeds the 2000000-byte limit")


@dataclass(frozen=True)
class SettingsSnapshot:
    """Immutable-by-convention settings values tied to one persisted revision."""

    path: Path
    values: dict[str, Any]
    revision: int

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)


class SettingsConflictError(AtomicDocumentConflictError):
    """Raised when a stale writer targets keys changed by another writer."""

    def __init__(
        self,
        *,
        keys: tuple[str, ...],
        expected_revision: int,
        actual_revision: int,
        reason: str = "",
    ):
        self.keys = keys
        self.expected_revision = int(expected_revision)
        self.actual_revision = int(actual_revision)
        if reason:
            detail = reason
        elif keys:
            detail = f"conflicting keys: {', '.join(keys)}"
        else:
            detail = "settings kept changing during the bounded merge retry"
        super().__init__(
            f"Settings revision {self.expected_revision} is stale; "
            f"current revision is {self.actual_revision} ({detail}). "
            "The persisted value was kept."
        )


class SettingsStore:
    """One versioned settings boundary with optimistic conflict-aware merges."""

    def __init__(
        self,
        filepath: str | Path = SETTINGS_FILE,
        *,
        conflict_retries: int = DEFAULT_CONFLICT_RETRIES,
    ):
        self.filepath = Path(filepath)
        self.conflict_retries = max(1, min(10, int(conflict_retries)))
        self._store = AtomicDocumentStore(
            self.filepath,
            schema=SETTINGS_SCHEMA,
            current_version=SETTINGS_SCHEMA_VERSION,
            default_factory=dict,
            migrations={0: _migrate_settings_v0},
            validator=_validate_settings,
        )

    @property
    def storage_status(self):
        return self._store.status

    def read(self) -> SettingsSnapshot:
        values = self._store.load()
        return SettingsSnapshot(
            path=self.filepath.resolve(),
            values=deepcopy(values),
            revision=self._store.revision,
        )

    @staticmethod
    def _key_changed(
        key: str,
        baseline: Mapping[str, Any],
        current: Mapping[str, Any],
    ) -> bool:
        baseline_has = key in baseline
        current_has = key in current
        return (
            baseline_has != current_has
            or (
                baseline_has
                and current_has
                and baseline[key] != current[key]
            )
        )

    def patch(
        self,
        changes: Mapping[str, Any],
        *,
        base_snapshot: SettingsSnapshot | None = None,
    ) -> SettingsSnapshot:
        """Merge a patch, rejecting stale same-key writes and retrying disjoint races."""
        requested = deepcopy(dict(changes))
        if not requested:
            return self.read()
        for key in requested:
            if not isinstance(key, str) or not key or len(key) > MAX_SETTINGS_KEY_CHARS:
                raise ValueError("settings patch keys must be non-empty bounded strings")

        baseline = base_snapshot or self.read()
        if baseline.path != self.filepath.resolve():
            raise ValueError("settings snapshot belongs to a different file")

        last_revision = baseline.revision
        for _attempt in range(self.conflict_retries):
            current = self.read()
            last_revision = current.revision
            if self._store.status.recovery_required:
                raise AtomicDocumentRecoveryError(self._store.status.error)
            conflicts = tuple(
                sorted(
                    key
                    for key, desired in requested.items()
                    if self._key_changed(key, baseline.values, current.values)
                    and current.values.get(key, object()) != desired
                )
            )
            if conflicts:
                raise SettingsConflictError(
                    keys=conflicts,
                    expected_revision=baseline.revision,
                    actual_revision=current.revision,
                )

            merged = deepcopy(current.values)
            merged.update(requested)
            _validate_settings(merged)
            if merged == current.values:
                return current
            try:
                revision = self._store.save(
                    merged,
                    expected_revision=current.revision,
                )
            except AtomicDocumentConflictError:
                continue
            return SettingsSnapshot(
                path=self.filepath.resolve(),
                values=deepcopy(merged),
                revision=revision,
            )

        raise SettingsConflictError(
            keys=(),
            expected_revision=baseline.revision,
            actual_revision=last_revision,
            reason=f"changed during {self.conflict_retries} merge attempts",
        )

    def set(
        self,
        key: str,
        value: Any,
        *,
        base_snapshot: SettingsSnapshot | None = None,
    ) -> SettingsSnapshot:
        return self.patch({key: value}, base_snapshot=base_snapshot)


def load_settings(filepath: str | Path = SETTINGS_FILE) -> dict[str, Any]:
    """Load current settings values through the versioned store."""
    return SettingsStore(filepath).read().values


def update_settings(
    changes: Mapping[str, Any],
    filepath: str | Path = SETTINGS_FILE,
    *,
    base_snapshot: SettingsSnapshot | None = None,
) -> SettingsSnapshot:
    """Apply a conflict-aware settings patch through the shared store."""
    return SettingsStore(filepath).patch(changes, base_snapshot=base_snapshot)
