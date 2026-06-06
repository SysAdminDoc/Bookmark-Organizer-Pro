"""Disabled-by-default update policy and readiness checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

from bookmark_organizer_pro.constants import APP_VERSION, DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.utils.runtime import atomic_json_write


UPDATE_CONFIG_FILE = DATA_DIR / "update_config.json"
UPDATE_CACHE_DIR = DATA_DIR / "updates"
UPDATE_APP_NAME = "BookmarkOrganizerPro"
DEFAULT_CHANNEL = "stable"
_CHANNEL_RE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")


def _clean_url(value: str) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("update repository URLs must use https")
    return parsed.geturl().rstrip("/")


def _clean_channel(value: str) -> str:
    channel = str(value or DEFAULT_CHANNEL).strip()
    if not _CHANNEL_RE.match(channel):
        raise ValueError("update channel must be 1-40 chars: letters, numbers, dot, dash, underscore")
    return channel


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = []
    for part in str(version or "").split("."):
        try:
            parts.append(int(part))
        except ValueError:
            break
    return tuple(parts or [0])


def is_newer_version(candidate: str, current: str = APP_VERSION) -> bool:
    """Return True when a dotted numeric candidate is newer than current."""
    return _version_tuple(candidate) > _version_tuple(current)


def tufup_available() -> bool:
    """Return whether the optional tufup runtime dependency is importable."""
    return importlib.util.find_spec("tufup") is not None


@dataclass(frozen=True)
class UpdatePolicy:
    enabled: bool
    metadata_url: str
    targets_url: str
    channel: str = DEFAULT_CHANNEL
    allow_prerelease: bool = False

    @property
    def configured(self) -> bool:
        return bool(self.metadata_url and self.targets_url)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "metadata_url": self.metadata_url,
            "targets_url": self.targets_url,
            "channel": self.channel,
            "allow_prerelease": self.allow_prerelease,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "UpdatePolicy":
        raw = data if isinstance(data, dict) else {}
        try:
            metadata_url = _clean_url(str(raw.get("metadata_url") or ""))
        except ValueError:
            metadata_url = ""
        try:
            targets_url = _clean_url(str(raw.get("targets_url") or ""))
        except ValueError:
            targets_url = ""
        try:
            channel = _clean_channel(str(raw.get("channel") or DEFAULT_CHANNEL))
        except ValueError:
            channel = DEFAULT_CHANNEL
        return cls(
            enabled=bool(raw.get("enabled", False)),
            metadata_url=metadata_url,
            targets_url=targets_url,
            channel=channel,
            allow_prerelease=bool(raw.get("allow_prerelease", False)),
        )


@dataclass(frozen=True)
class UpdateStatus:
    policy: UpdatePolicy
    current_version: str
    cache_dir: str
    metadata_dir: str
    target_dir: str
    trusted_root_exists: bool
    tufup_installed: bool
    can_check: bool
    reason: str
    checked_at: str


@dataclass(frozen=True)
class UpdateCheckResult:
    checked: bool
    update_available: bool
    current_version: str
    latest_version: str
    target_name: str
    target_path: str
    reason: str
    error: str = ""


@dataclass(frozen=True)
class UpdateDownloadResult:
    checked: bool
    update_available: bool
    downloaded: bool
    current_version: str
    latest_version: str
    target_name: str
    target_path: str
    staged_paths: tuple[str, ...]
    reason: str
    error: str = ""


@dataclass(frozen=True)
class StagedUpdateStatus:
    available: bool
    complete: bool
    current_version: str
    latest_version: str
    target_name: str
    target_path: str
    staged_paths: tuple[str, ...]
    manifest_path: str
    channel: str
    staged_at: str
    reason: str
    error: str = ""


@dataclass(frozen=True)
class UpdateApplyPreflightResult:
    allowed: bool
    current_version: str
    latest_version: str
    target_name: str
    staged_paths: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class UpdateCleanupResult:
    cleaned: bool
    removed_manifest: bool
    removed_targets: tuple[str, ...]
    errors: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class UpdateApplyPlan:
    ready: bool
    current_version: str
    latest_version: str
    target_name: str
    install_dir: str
    rollback_dir: str
    staged_paths: tuple[str, ...]
    actions: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str


class UpdateManager:
    """Manage local update policy without applying updates automatically."""

    def __init__(
        self,
        config_file=UPDATE_CONFIG_FILE,
        cache_dir=UPDATE_CACHE_DIR,
        current_version: str = APP_VERSION,
    ):
        self.config_file = Path(config_file)
        self.cache_dir = Path(cache_dir)
        self.current_version = current_version
        self.policy = self._load_policy()

    @property
    def metadata_dir(self) -> Path:
        return self.cache_dir / "metadata"

    @property
    def target_dir(self) -> Path:
        return self.cache_dir / "targets"

    @property
    def trusted_root_path(self) -> Path:
        return self.metadata_dir / "root.json"

    @property
    def staged_manifest_path(self) -> Path:
        return self.cache_dir / "staged_update.json"

    @property
    def rollback_dir(self) -> Path:
        return self.cache_dir / "rollback"

    def _load_policy(self) -> UpdatePolicy:
        if not self.config_file.exists():
            return UpdatePolicy(False, "", "", DEFAULT_CHANNEL, False)
        try:
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning(f"Could not load update config: {exc}")
            data = {}
        return UpdatePolicy.from_dict(data)

    def save_policy(self) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        atomic_json_write(self.config_file, self.policy.to_dict())

    def configure(
        self,
        *,
        enabled: bool | None = None,
        metadata_url: str | None = None,
        targets_url: str | None = None,
        channel: str | None = None,
        allow_prerelease: bool | None = None,
    ) -> UpdatePolicy:
        policy = self.policy
        self.policy = UpdatePolicy(
            enabled=policy.enabled if enabled is None else bool(enabled),
            metadata_url=policy.metadata_url if metadata_url is None else _clean_url(metadata_url),
            targets_url=policy.targets_url if targets_url is None else _clean_url(targets_url),
            channel=policy.channel if channel is None else _clean_channel(channel),
            allow_prerelease=(
                policy.allow_prerelease if allow_prerelease is None else bool(allow_prerelease)
            ),
        )
        self.save_policy()
        return self.policy

    def status(self) -> UpdateStatus:
        installed = tufup_available()
        root_exists = self.trusted_root_path.exists()
        if not self.policy.enabled:
            can_check = False
            reason = "disabled"
        elif not self.policy.configured:
            can_check = False
            reason = "repository not configured"
        elif not installed:
            can_check = False
            reason = "install bookmark-organizer-pro[updates]"
        elif not root_exists:
            can_check = False
            reason = "trusted root metadata missing"
        else:
            can_check = True
            reason = "ready"
        return UpdateStatus(
            policy=self.policy,
            current_version=self.current_version,
            cache_dir=str(self.cache_dir),
            metadata_dir=str(self.metadata_dir),
            target_dir=str(self.target_dir),
            trusted_root_exists=root_exists,
            tufup_installed=installed,
            can_check=can_check,
            reason=reason,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def _pre_release_level(self) -> str | None:
        return "a" if self.policy.allow_prerelease else None

    def _build_client(self, client_cls=None):
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.target_dir.mkdir(parents=True, exist_ok=True)
        if client_cls is None:
            from tufup.client import Client as client_cls
        return client_cls(
            app_name=UPDATE_APP_NAME,
            app_install_dir=Path(sys.executable).resolve().parent,
            current_version=self.current_version,
            metadata_dir=self.metadata_dir,
            metadata_base_url=self.policy.metadata_url,
            target_dir=self.target_dir,
            target_base_url=self.policy.targets_url,
        )

    def _run_update_check(self, client):
        return client.check_for_updates(pre=self._pre_release_level(), patch=True)

    def _check_result_from_target(self, target_meta) -> UpdateCheckResult:
        if target_meta is None:
            return UpdateCheckResult(
                checked=True,
                update_available=False,
                current_version=self.current_version,
                latest_version="",
                target_name="",
                target_path="",
                reason="no update available",
            )
        return UpdateCheckResult(
            checked=True,
            update_available=True,
            current_version=self.current_version,
            latest_version=str(getattr(target_meta, "version", "")),
            target_name=str(getattr(target_meta, "filename", "")),
            target_path=str(getattr(target_meta, "target_path_str", "")),
            reason="update available",
        )

    def _download_result_from_check(
        self,
        check: UpdateCheckResult,
        *,
        downloaded: bool = False,
        staged_paths: tuple[str, ...] = (),
        reason: str | None = None,
        error: str = "",
    ) -> UpdateDownloadResult:
        return UpdateDownloadResult(
            checked=check.checked,
            update_available=check.update_available,
            downloaded=downloaded,
            current_version=check.current_version,
            latest_version=check.latest_version,
            target_name=check.target_name,
            target_path=check.target_path,
            staged_paths=staged_paths,
            reason=check.reason if reason is None else reason,
            error=error or check.error,
        )

    def _selected_target_infos(self, client) -> list:
        targets = getattr(client, "new_targets", None)
        if isinstance(targets, dict) and targets:
            return list(targets.values())
        archive_info = getattr(client, "new_archive_info", None)
        return [archive_info] if archive_info is not None else []

    def _ensure_staged_path(self, path_value: str) -> str:
        path = Path(path_value)
        target_root = self.target_dir.resolve()
        resolved = path.resolve()
        try:
            resolved.relative_to(target_root)
        except ValueError as exc:
            raise ValueError("downloaded target escaped the update target cache") from exc
        return str(resolved)

    def _write_staged_manifest(
        self,
        check: UpdateCheckResult,
        staged_paths: tuple[str, ...],
    ) -> None:
        atomic_json_write(
            self.staged_manifest_path,
            {
                "current_version": check.current_version,
                "latest_version": check.latest_version,
                "target_name": check.target_name,
                "target_path": check.target_path,
                "staged_paths": list(staged_paths),
                "channel": self.policy.channel,
                "staged_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def staged_update(self) -> StagedUpdateStatus:
        """Return the locally staged update manifest and file readiness."""
        manifest_path = self.staged_manifest_path
        empty = StagedUpdateStatus(
            available=False,
            complete=False,
            current_version=self.current_version,
            latest_version="",
            target_name="",
            target_path="",
            staged_paths=(),
            manifest_path=str(manifest_path),
            channel=self.policy.channel,
            staged_at="",
            reason="no staged update",
        )
        if not manifest_path.exists():
            return empty
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return StagedUpdateStatus(
                **{**empty.__dict__, "reason": "staged manifest unreadable",
                   "error": f"{type(exc).__name__}: {exc}"}
            )
        if not isinstance(raw, dict):
            return StagedUpdateStatus(
                **{**empty.__dict__, "reason": "staged manifest invalid"}
            )
        try:
            staged_paths = tuple(
                self._ensure_staged_path(path)
                for path in raw.get("staged_paths", [])
                if str(path or "").strip()
            )
        except Exception as exc:
            return StagedUpdateStatus(
                **{**empty.__dict__, "reason": "staged manifest invalid",
                   "error": f"{type(exc).__name__}: {exc}"}
            )
        latest_version = str(raw.get("latest_version") or "")
        manifest_current = str(raw.get("current_version") or "")
        missing_paths = [path for path in staged_paths if not Path(path).exists()]
        complete = bool(
            latest_version
            and staged_paths
            and not missing_paths
            and manifest_current == self.current_version
        )
        if manifest_current and manifest_current != self.current_version:
            reason = "staged update targets a different current version"
        elif missing_paths:
            reason = "staged target files missing"
        elif not latest_version or not staged_paths:
            reason = "staged manifest incomplete"
        else:
            reason = "staged target files present"
        return StagedUpdateStatus(
            available=True,
            complete=complete,
            current_version=manifest_current,
            latest_version=latest_version,
            target_name=str(raw.get("target_name") or ""),
            target_path=str(raw.get("target_path") or ""),
            staged_paths=staged_paths,
            manifest_path=str(manifest_path),
            channel=str(raw.get("channel") or self.policy.channel),
            staged_at=str(raw.get("staged_at") or ""),
            reason=reason,
        )

    def apply_preflight(self) -> UpdateApplyPreflightResult:
        """Report staged update readiness without applying any files."""
        staged = self.staged_update()
        blockers = []
        if not staged.available:
            blockers.append(staged.reason)
        elif not staged.complete:
            blockers.append(staged.reason)
        blockers.append("update application is disabled in this release")
        return UpdateApplyPreflightResult(
            allowed=False,
            current_version=self.current_version,
            latest_version=staged.latest_version,
            target_name=staged.target_name,
            staged_paths=staged.staged_paths,
            blockers=tuple(blockers),
            reason="apply gated",
        )

    def clear_staged_update(self, *, remove_targets: bool = True) -> UpdateCleanupResult:
        """Remove staged update manifest and cached staged targets only."""
        staged = self.staged_update()
        removed_targets = []
        errors = []
        if remove_targets:
            for path_value in staged.staged_paths:
                try:
                    path = Path(self._ensure_staged_path(path_value))
                    if path.exists():
                        path.unlink()
                        removed_targets.append(str(path))
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
        removed_manifest = False
        try:
            if self.staged_manifest_path.exists():
                self.staged_manifest_path.unlink()
                removed_manifest = True
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        cleaned = bool(removed_manifest or removed_targets)
        if errors:
            reason = "staged update cleanup incomplete"
        elif cleaned:
            reason = "staged update cleared"
        else:
            reason = "no staged update"
        return UpdateCleanupResult(
            cleaned=cleaned,
            removed_manifest=removed_manifest,
            removed_targets=tuple(removed_targets),
            errors=tuple(errors),
            reason=reason,
        )

    def build_apply_plan(self, install_dir: str | Path | None = None) -> UpdateApplyPlan:
        """Build a non-mutating apply and rollback plan for staged targets."""
        preflight = self.apply_preflight()
        install_path = Path(install_dir).expanduser() if install_dir else Path(sys.executable).resolve().parent
        install_path = install_path.resolve()
        latest = preflight.latest_version or "unknown"
        rollback_path = (self.rollback_dir / f"{self.current_version}-to-{latest}").resolve()
        actions = (
            "verify staged target files",
            f"create rollback snapshot under {rollback_path}",
            f"extract staged update target into a temporary directory under {self.cache_dir.resolve()}",
            f"replace files in {install_path}",
            "verify application version after replacement",
            "remove staged update artifacts after successful replacement",
        )
        return UpdateApplyPlan(
            ready=False,
            current_version=self.current_version,
            latest_version=preflight.latest_version,
            target_name=preflight.target_name,
            install_dir=str(install_path),
            rollback_dir=str(rollback_path),
            staged_paths=preflight.staged_paths,
            actions=actions,
            blockers=preflight.blockers,
            reason="apply plan only",
        )

    def check_for_updates(self, client_cls=None) -> UpdateCheckResult:
        """Check trusted metadata for an available update without downloading."""
        status = self.status()
        if not status.can_check:
            return UpdateCheckResult(
                checked=False,
                update_available=False,
                current_version=self.current_version,
                latest_version="",
                target_name="",
                target_path="",
                reason=status.reason,
            )
        try:
            client = self._build_client(client_cls)
            target_meta = self._run_update_check(client)
        except Exception as exc:
            return UpdateCheckResult(
                checked=True,
                update_available=False,
                current_version=self.current_version,
                latest_version="",
                target_name="",
                target_path="",
                reason="check failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        return self._check_result_from_target(target_meta)

    def download_update(self, client_cls=None) -> UpdateDownloadResult:
        """Stage trusted update targets in the cache without applying them."""
        status = self.status()
        if not status.can_check:
            check = UpdateCheckResult(
                checked=False,
                update_available=False,
                current_version=self.current_version,
                latest_version="",
                target_name="",
                target_path="",
                reason=status.reason,
            )
            return self._download_result_from_check(check)
        try:
            client = self._build_client(client_cls)
            target_meta = self._run_update_check(client)
            check = self._check_result_from_target(target_meta)
            if not check.update_available:
                return self._download_result_from_check(check)
            target_infos = self._selected_target_infos(client)
            if not target_infos:
                return self._download_result_from_check(
                    check,
                    reason="download target metadata unavailable",
                )
            staged_paths = []
            for target_info in target_infos:
                staged_path = client.download_target(
                    target_info,
                    target_base_url=self.policy.targets_url,
                )
                staged_paths.append(self._ensure_staged_path(staged_path))
            staged_paths_tuple = tuple(staged_paths)
            self._write_staged_manifest(check, staged_paths_tuple)
        except Exception as exc:
            fallback = locals().get(
                "check",
                UpdateCheckResult(
                    checked=True,
                    update_available=False,
                    current_version=self.current_version,
                    latest_version="",
                    target_name="",
                    target_path="",
                    reason="download failed",
                ),
            )
            return self._download_result_from_check(
                fallback,
                downloaded=False,
                reason="download failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        return self._download_result_from_check(
            check,
            downloaded=True,
            staged_paths=staged_paths_tuple,
            reason="download staged",
        )
