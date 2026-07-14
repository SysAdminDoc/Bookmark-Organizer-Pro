"""Checksummed, portable full-library backup and restore bundles."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from bookmark_organizer_pro import constants as app_constants


BUNDLE_FORMAT = "bookmark-organizer-recovery"
BUNDLE_VERSION = 2
SUPPORTED_BUNDLE_VERSIONS = {1, BUNDLE_VERSION}
MANIFEST_NAME = "recovery-manifest.json"
INDEX_NAME = "library-index.json"
PAYLOAD_PREFIX = "library"
ROLLBACK_FORMAT = "bookmark-organizer-restore-checkpoint"
ROLLBACK_VERSION = 1
ROLLBACK_MANIFEST_NAME = "rollback-manifest.json"
MAX_MEMBERS = 100_000
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024 * 1024

# Explicitly omit credentials (ai_config/api_token/mcp_tokens), logs, caches,
# exports and rolling backups. Rebuildable vector indexes are described by the
# generated library index instead of being copied.
LIBRARY_FILES = (
    "master_bookmarks.json",
    "master_bookmarks.sqlite",
    "categories.json",
    "tags.json",
    "settings.json",
    "patterns.json",
    "reader_annotations.json",
    "flows.json",
    "feeds.json",
    "smart_collections.json",
    "collections.json",
    "smart_tag_rules.json",
    "settings_profiles.json",
    "category_colors.json",
    "snapshot_schedule.json",
    "extraction_templates.json",
    "dead_links.json",
    "snapshot_failures.json",
    "snapshot_history.json",
    "import_sessions.json",
)
LIBRARY_DIRS = ("snapshots", "extracted", "ai_snapshots")


@dataclass(frozen=True)
class BundleReport:
    """Result of validation or restore preflight."""

    valid: bool
    bundle_version: int | None = None
    file_count: int = 0
    total_bytes: int = 0
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    contents: tuple[str, ...] = ()
    rebuild: dict[str, Any] = field(default_factory=dict)
    storage_backend: str = ""
    actions: tuple["RestoreAction", ...] = ()


@dataclass(frozen=True)
class RestoreAction:
    """One observable mutation proposed by recovery preflight."""

    kind: str
    path: str
    detail: str = ""


@dataclass(frozen=True)
class RestoreResult:
    """Restore outcome; ``applied`` is false for every dry run."""

    report: BundleReport
    applied: bool = False
    rollback_bundle: str = ""
    storage_backend: str = ""
    restored_count: int = 0


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_member(archive: zipfile.ZipFile, name: str) -> str:
    digest = hashlib.sha256()
    with archive.open(name, "r") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: str) -> PurePosixPath | None:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        return None
    return path


def _source_storage_backend(data_dir: Path) -> str:
    """Resolve the one live backend that a newly created bundle represents."""

    json_exists = (data_dir / "master_bookmarks.json").is_file()
    sqlite_exists = (data_dir / "master_bookmarks.sqlite").is_file()
    requested = os.getenv("BOOKMARK_STORAGE_BACKEND", "").strip().lower()
    if requested in {"sqlite", "sqlite3"} and sqlite_exists:
        return "sqlite"
    if requested == "json" and json_exists:
        return "json"
    if json_exists:
        return "json"
    if sqlite_exists:
        return "sqlite"
    raise ValueError(f"No bookmark library found under {data_dir}")


def _backend_filename(backend: str) -> str:
    return "master_bookmarks.sqlite" if backend == "sqlite" else "master_bookmarks.json"


def _payload_files(data_dir: Path) -> list[tuple[Path, str]]:
    backend = _source_storage_backend(data_dir)
    selected_library = _backend_filename(backend)
    files: list[tuple[Path, str]] = []
    for name in LIBRARY_FILES:
        if name in {"master_bookmarks.json", "master_bookmarks.sqlite"} and name != selected_library:
            continue
        path = data_dir / name
        if path.is_file():
            files.append((path, name))
    for dirname in LIBRARY_DIRS:
        root = data_dir / dirname
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and not path.is_symlink():
                files.append((path, path.relative_to(data_dir).as_posix()))
    return sorted(files, key=lambda item: item[1])


def _managed_files(data_dir: Path) -> list[tuple[Path, str]]:
    """Return every current file governed by an exact-state restore."""

    files: list[tuple[Path, str]] = []
    for name in LIBRARY_FILES:
        path = data_dir / name
        if path.is_symlink():
            raise ValueError(f"Managed library path may not be a symbolic link: {path}")
        if path.is_file():
            files.append((path, name))
    for dirname in LIBRARY_DIRS:
        root = data_dir / dirname
        if root.is_symlink():
            raise ValueError(f"Managed library path may not be a symbolic link: {root}")
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Managed library path may not be a symbolic link: {path}")
            if path.is_file():
                files.append((path, path.relative_to(data_dir).as_posix()))
    return sorted(files, key=lambda item: item[1])


def _portable_path_index(data_dir: Path) -> list[dict[str, str]]:
    library = data_dir / "master_bookmarks.json"
    items: list[Any] = []
    if library.is_file():
        try:
            raw = json.loads(library.read_text(encoding="utf-8"))
            items = raw if isinstance(raw, list) else raw.get("data", [])
        except (OSError, json.JSONDecodeError, AttributeError):
            items = []
    elif (data_dir / "master_bookmarks.sqlite").is_file():
        try:
            with closing(sqlite3.connect(data_dir / "master_bookmarks.sqlite")) as connection:
                items = [
                    json.loads(row[0])
                    for row in connection.execute("SELECT payload_json FROM bookmarks")
                ]
        except (sqlite3.Error, json.JSONDecodeError, OSError):
            items = []
    rewrites: list[dict[str, str]] = []
    root = data_dir.resolve()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        for field_name in ("snapshot_path", "extracted_text_path"):
            value = item.get(field_name)
            if not value:
                continue
            try:
                relative = Path(value).expanduser().resolve().relative_to(root).as_posix()
            except (OSError, ValueError):
                continue
            if (data_dir / relative).is_file():
                rewrites.append({
                    "bookmark_id": str(item.get("id", "")),
                    "field": field_name,
                    "relative_path": relative,
                })
    return rewrites


def create_recovery_bundle(
    destination: str | Path,
    *,
    data_dir: str | Path | None = None,
) -> Path:
    """Create an atomic, checksummed library bundle and validate it."""

    root = Path(data_dir or app_constants.DATA_DIR).expanduser().resolve()
    destination = Path(destination).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    storage_backend = _source_storage_backend(root)
    payloads = _payload_files(root)

    generated_index = {
        "format_version": 1,
        "portable_paths": _portable_path_index(root),
        "rebuild": {
            "embeddings": True,
            "full_text_index": True,
            "reason": "Search indexes are rebuildable and intentionally excluded from recovery bundles.",
        },
        "excluded_sensitive": ["ai_config.json", "api_token.txt", "mcp_tokens.json"],
    }
    index_bytes = json.dumps(generated_index, indent=2, ensure_ascii=False).encode("utf-8")
    entries: list[dict[str, Any]] = []
    fd, temp_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=destination.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temp_name, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for source, relative in payloads:
                archive_name = f"{PAYLOAD_PREFIX}/{relative}"
                size = source.stat().st_size
                digest = _hash_file(source)
                archive.write(source, archive_name)
                entries.append({
                    "path": archive_name,
                    "relative_path": relative,
                    "size": size,
                    "sha256": digest,
                })
            archive.writestr(INDEX_NAME, index_bytes)
            entries.append({
                "path": INDEX_NAME,
                "relative_path": "",
                "size": len(index_bytes),
                "sha256": _sha256(index_bytes),
            })
            manifest = {
                "format": BUNDLE_FORMAT,
                "version": BUNDLE_VERSION,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "storage_backend": storage_backend,
                "entries": entries,
            }
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, ensure_ascii=False))
        report = validate_recovery_bundle(temp_name)
        if not report.valid:
            raise ValueError("Created recovery bundle failed validation: " + "; ".join(report.errors))
        os.replace(temp_name, destination)
    finally:
        try:
            Path(temp_name).unlink(missing_ok=True)
        except OSError:
            pass
    return destination


def validate_recovery_bundle(bundle_path: str | Path) -> BundleReport:
    """Verify structure, supported version, member paths, sizes and hashes."""

    errors: list[str] = []
    warnings: list[str] = []
    contents: list[str] = []
    version: int | None = None
    storage_backend = ""
    total = 0
    rebuild: dict[str, Any] = {}
    try:
        with zipfile.ZipFile(Path(bundle_path).expanduser(), "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                errors.append("Bundle contains duplicate member names")
            if len(infos) > MAX_MEMBERS:
                errors.append(f"Bundle contains too many members ({len(infos)} > {MAX_MEMBERS})")
            total = sum(info.file_size for info in infos)
            if total > MAX_UNCOMPRESSED_BYTES:
                errors.append("Bundle uncompressed size exceeds the 50 GiB safety limit")
            for info in infos:
                if _safe_relative(info.filename) is None:
                    errors.append(f"Unsafe archive path: {info.filename}")
                if info.flag_bits & 0x1:
                    errors.append(f"Encrypted archive member is unsupported: {info.filename}")
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    errors.append(f"Symbolic links are unsupported: {info.filename}")
            if MANIFEST_NAME not in names:
                errors.append(f"Missing {MANIFEST_NAME}")
                return BundleReport(False, errors=tuple(errors), total_bytes=total)
            try:
                manifest = json.loads(archive.read(MANIFEST_NAME))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                errors.append(f"Invalid manifest JSON: {exc}")
                return BundleReport(False, errors=tuple(errors), total_bytes=total)
            if manifest.get("format") != BUNDLE_FORMAT:
                errors.append("Unsupported recovery bundle format")
            version = manifest.get("version")
            if version not in SUPPORTED_BUNDLE_VERSIONS:
                errors.append(
                    f"Unsupported recovery bundle version {version!r}; "
                    f"supported versions are {sorted(SUPPORTED_BUNDLE_VERSIONS)}"
                )
            entries = manifest.get("entries")
            if not isinstance(entries, list):
                errors.append("Manifest entries must be an array")
                entries = []
            expected_names = {MANIFEST_NAME}
            library_backends: set[str] = set()
            for position, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    errors.append(f"Manifest entry {position} is not an object")
                    continue
                name = entry.get("path", "")
                if _safe_relative(name) is None or name == MANIFEST_NAME:
                    errors.append(f"Manifest entry {position} has an unsafe path")
                    continue
                expected_names.add(name)
                if name not in names:
                    errors.append(f"Missing payload: {name}")
                    continue
                info = archive.getinfo(name)
                if info.file_size != entry.get("size"):
                    errors.append(f"Size mismatch: {name}")
                if _hash_member(archive, name) != entry.get("sha256"):
                    errors.append(f"Checksum mismatch: {name}")
                relative = entry.get("relative_path", "")
                if name.startswith(f"{PAYLOAD_PREFIX}/"):
                    if _safe_relative(relative) is None or name != f"{PAYLOAD_PREFIX}/{relative}":
                        errors.append(f"Invalid restore path mapping: {name}")
                    else:
                        contents.append(relative)
                        if relative == "master_bookmarks.json":
                            library_backends.add("json")
                        elif relative == "master_bookmarks.sqlite":
                            library_backends.add("sqlite")
            extras = sorted(set(names) - expected_names)
            if extras:
                errors.append("Unmanifested archive members: " + ", ".join(extras[:5]))
            if not library_backends:
                errors.append("Bundle does not contain a bookmark library")
            elif len(library_backends) != 1:
                errors.append("Bundle must contain exactly one bookmark storage backend")
            else:
                inferred_backend = next(iter(library_backends))
                declared_backend = manifest.get("storage_backend", "")
                if version == 1 and not declared_backend:
                    storage_backend = inferred_backend
                    warnings.append(
                        f"Legacy bundle backend inferred as {storage_backend}; apply will upgrade semantics"
                    )
                elif declared_backend not in {"json", "sqlite"}:
                    errors.append("Bundle storage_backend must be 'json' or 'sqlite'")
                elif declared_backend != inferred_backend:
                    errors.append(
                        f"Bundle storage_backend {declared_backend!r} does not match its library payload"
                    )
                else:
                    storage_backend = declared_backend
            if INDEX_NAME not in names:
                errors.append(f"Missing {INDEX_NAME}")
            else:
                try:
                    index = json.loads(archive.read(INDEX_NAME))
                    rebuild = index.get("rebuild", {}) if isinstance(index, dict) else {}
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    errors.append(f"Invalid library index: {exc}")
            for expected in ("categories.json", "tags.json", "settings.json", "reader_annotations.json"):
                if expected not in contents:
                    warnings.append(f"Optional library component is absent: {expected}")
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        errors.append(f"Could not open recovery bundle: {exc}")
    return BundleReport(
        not errors,
        bundle_version=version,
        file_count=len(contents),
        total_bytes=total,
        errors=tuple(errors),
        warnings=tuple(warnings),
        contents=tuple(sorted(contents)),
        rebuild=rebuild,
        storage_backend=storage_backend,
    )


def _rewrite_portable_paths(staging: Path, target: Path, index: dict[str, Any]) -> None:
    history_path = staging / "snapshot_history.json"
    if history_path.is_file():
        from bookmark_organizer_pro.services.snapshot_history import SnapshotHistoryStore
        SnapshotHistoryStore(staging / "snapshots").relocate_paths(target / "snapshots")
    rewrites = index.get("portable_paths", [])
    if not isinstance(rewrites, list) or not rewrites:
        return
    json_path = staging / "master_bookmarks.json"
    if json_path.is_file():
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("data", [])
        lookup = {(str(item.get("id", "")), field): item for item in items if isinstance(item, dict) for field in ("snapshot_path", "extracted_text_path")}
        for rewrite in rewrites:
            relative = rewrite.get("relative_path", "")
            if _safe_relative(relative) is None:
                continue
            item = lookup.get((str(rewrite.get("bookmark_id", "")), rewrite.get("field", "")))
            if item is not None:
                item[rewrite["field"]] = str((target / relative).resolve())
        json_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    sqlite_path = staging / "master_bookmarks.sqlite"
    if sqlite_path.is_file():
        with closing(sqlite3.connect(sqlite_path)) as connection:
            rows = connection.execute("SELECT id, payload_json FROM bookmarks").fetchall()
            rewrite_lookup = {(str(item.get("bookmark_id", "")), item.get("field", "")): item.get("relative_path", "") for item in rewrites if isinstance(item, dict)}
            for bookmark_id, encoded in rows:
                payload = json.loads(encoded)
                changed = False
                for field_name in ("snapshot_path", "extracted_text_path"):
                    relative = rewrite_lookup.get((str(bookmark_id), field_name))
                    if relative and _safe_relative(relative) is not None:
                        payload[field_name] = str((target / relative).resolve())
                        changed = True
                if changed:
                    connection.execute("UPDATE bookmarks SET payload_json=? WHERE id=?", (json.dumps(payload, ensure_ascii=False, separators=(",", ":")), str(bookmark_id)))
            connection.commit()


def _bundle_payload_entries(bundle_path: str | Path) -> dict[str, dict[str, Any]]:
    with zipfile.ZipFile(bundle_path, "r") as archive:
        manifest = json.loads(archive.read(MANIFEST_NAME))
    return {
        str(entry["relative_path"]): entry
        for entry in manifest.get("entries", [])
        if isinstance(entry, dict) and entry.get("relative_path")
    }


def _plan_restore_actions(
    bundle_path: str | Path,
    target: Path,
    report: BundleReport,
) -> tuple[RestoreAction, ...]:
    entries = _bundle_payload_entries(bundle_path)
    expected = set(entries)
    actions: list[RestoreAction] = []
    alternate = "master_bookmarks.sqlite" if report.storage_backend == "json" else "master_bookmarks.json"
    if (target / alternate).exists():
        actions.append(RestoreAction(
            "backend-switch",
            _backend_filename(report.storage_backend),
            f"activate {report.storage_backend} and retire {alternate}",
        ))
    for relative, entry in sorted(entries.items()):
        path = target / relative
        if not path.is_file():
            actions.append(RestoreAction("create", relative, "install bundle member"))
        elif _hash_file(path) != entry.get("sha256"):
            actions.append(RestoreAction("update", relative, "replace with bundle member"))
    current = {relative for _, relative in _managed_files(target)}
    for relative in sorted(current - expected):
        actions.append(RestoreAction("delete", relative, "absent from exact recovery state"))
    for dirname in LIBRARY_DIRS:
        path = target / dirname
        if path.is_dir() and not any(item == dirname or item.startswith(dirname + "/") for item in expected):
            if not any(action.kind == "delete" and action.path.startswith(dirname + "/") for action in actions):
                actions.append(RestoreAction("delete", dirname, "empty managed directory is absent from bundle"))
    order = {"backend-switch": 0, "create": 1, "update": 2, "delete": 3}
    return tuple(sorted(actions, key=lambda action: (order[action.kind], action.path)))


def _create_restore_checkpoint(target: Path, destination: Path) -> Path:
    """Write and re-read an exact snapshot of current managed state."""

    payloads = _managed_files(target)
    roots = [
        name for name in (*LIBRARY_FILES, *LIBRARY_DIRS)
        if (target / name).exists() or (target / name).is_symlink()
    ]
    entries: list[dict[str, Any]] = []
    fd, temp_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=destination.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temp_name, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for source, relative in payloads:
                name = f"{PAYLOAD_PREFIX}/{relative}"
                archive.write(source, name)
                entries.append({
                    "path": name,
                    "relative_path": relative,
                    "size": source.stat().st_size,
                    "sha256": _hash_file(source),
                })
            manifest = {
                "format": ROLLBACK_FORMAT,
                "version": ROLLBACK_VERSION,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "roots": roots,
                "entries": entries,
            }
            archive.writestr(ROLLBACK_MANIFEST_NAME, json.dumps(manifest, indent=2, ensure_ascii=False))
        with zipfile.ZipFile(temp_name, "r") as archive:
            manifest = json.loads(archive.read(ROLLBACK_MANIFEST_NAME))
            expected_names = {ROLLBACK_MANIFEST_NAME}
            if manifest.get("format") != ROLLBACK_FORMAT or manifest.get("version") != ROLLBACK_VERSION:
                raise ValueError("Rollback checkpoint manifest is invalid")
            for entry in manifest.get("entries", []):
                expected_names.add(entry["path"])
                info = archive.getinfo(entry["path"])
                if info.file_size != entry["size"] or _hash_member(archive, entry["path"]) != entry["sha256"]:
                    raise ValueError(f"Rollback checkpoint verification failed: {entry['relative_path']}")
            if set(archive.namelist()) != expected_names:
                raise ValueError("Rollback checkpoint contains unmanifested members")
        os.replace(temp_name, destination)
    finally:
        Path(temp_name).unlink(missing_ok=True)
    return destination


def _validate_restored_state(
    root: Path,
    backend: str,
    expected_paths: set[str],
) -> tuple[tuple[int, ...], dict[str, str]]:
    """Open the selected backend and fingerprint the exact managed fixture."""

    from bookmark_organizer_pro.core import SQLiteStorageManager, StorageManager

    selected = root / _backend_filename(backend)
    alternate = root / _backend_filename("json" if backend == "sqlite" else "sqlite")
    if not selected.is_file() or alternate.exists():
        raise ValueError(f"Restored state is not a single {backend} backend")
    storage = SQLiteStorageManager(selected) if backend == "sqlite" else StorageManager(selected)
    bookmarks = storage.load()
    status = getattr(storage, "status", None)
    if status is not None and getattr(status, "recovery_required", False):
        raise ValueError(f"Restored backend failed to reopen: {getattr(status, 'error', 'invalid state')}")
    ids = tuple(sorted(int(bookmark.id) for bookmark in bookmarks))
    if len(ids) != len(set(ids)):
        raise ValueError("Restored backend contains duplicate bookmark IDs")
    expected_count = getattr(status, "count", len(bookmarks)) if status is not None else len(bookmarks)
    if expected_count != len(bookmarks):
        raise ValueError(
            f"Restored backend count mismatch: storage={expected_count}, loaded={len(bookmarks)}"
        )
    actual_files = {relative for _, relative in _managed_files(root)}
    if actual_files != expected_paths:
        missing = sorted(expected_paths - actual_files)
        extra = sorted(actual_files - expected_paths)
        raise ValueError(f"Restored managed-state mismatch; missing={missing[:3]}, extra={extra[:3]}")
    checksums = {relative: _hash_file(root / relative) for relative in sorted(expected_paths)}
    return ids, checksums


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def restore_recovery_bundle(
    bundle_path: str | Path,
    *,
    data_dir: str | Path | None = None,
    dry_run: bool = True,
) -> RestoreResult:
    """Preflight or transactionally install one exact managed-library state."""

    report = validate_recovery_bundle(bundle_path)
    target = Path(data_dir or app_constants.DATA_DIR).expanduser().resolve()
    if report.valid:
        report = replace(report, actions=_plan_restore_actions(bundle_path, target, report))
    if dry_run or not report.valid:
        return RestoreResult(report=report, storage_backend=report.storage_backend)
    target.mkdir(parents=True, exist_ok=True)
    rollback_dir = target / "backups" / "recovery_bundles"
    rollback_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    rollback = rollback_dir / f"pre_restore_{stamp}.zip"

    with tempfile.TemporaryDirectory(prefix="bop-restore-", dir=target.parent) as temp:
        transaction = Path(temp)
        staging = transaction / "candidate"
        staging.mkdir()
        prior = transaction / "prior"
        prior.mkdir()
        with zipfile.ZipFile(bundle_path, "r") as archive:
            manifest = json.loads(archive.read(MANIFEST_NAME))
            index = json.loads(archive.read(INDEX_NAME))
            extracted: set[str] = set()
            for entry in manifest["entries"]:
                relative = entry.get("relative_path", "")
                if not relative:
                    continue
                output = staging / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry["path"], "r") as source, output.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
                if output.stat().st_size != entry.get("size") or _hash_file(output) != entry.get("sha256"):
                    raise ValueError(f"Bundle changed during restore extraction: {relative}")
                extracted.add(relative)
        expected_paths = set(report.contents)
        if extracted != expected_paths:
            raise ValueError("Extracted bundle members do not match validated recovery contents")
        _rewrite_portable_paths(staging, target, index)
        staged_ids, staged_checksums = _validate_restored_state(
            staging,
            report.storage_backend,
            expected_paths,
        )
        _create_restore_checkpoint(target, rollback)

        managed_roots = tuple(dict.fromkeys((*LIBRARY_FILES, *LIBRARY_DIRS)))
        candidate_roots = tuple(sorted({PurePosixPath(path).parts[0] for path in expected_paths}))
        moved_prior: list[str] = []
        installed: list[str] = []
        try:
            for name in managed_roots:
                current = target / name
                if current.exists() or current.is_symlink():
                    destination = prior / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(current, destination)
                    moved_prior.append(name)
            for name in candidate_roots:
                source = staging / name
                destination = target / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, destination)
                installed.append(name)
            installed_ids, installed_checksums = _validate_restored_state(
                target,
                report.storage_backend,
                expected_paths,
            )
            if installed_ids != staged_ids or installed_checksums != staged_checksums:
                raise ValueError("Installed recovery state differs from its validated staging fixture")
        except Exception:
            for name in reversed(installed):
                _remove_path(target / name)
            for name in reversed(moved_prior):
                destination = target / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(prior / name, destination)
            raise
    return RestoreResult(
        report=report,
        applied=True,
        rollback_bundle=str(rollback),
        storage_backend=report.storage_backend,
        restored_count=len(staged_ids),
    )
