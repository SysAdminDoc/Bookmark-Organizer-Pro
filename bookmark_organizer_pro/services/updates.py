"""Disabled-by-default update policy and readiness checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.util
import json
import re
from urllib.parse import urlparse

from bookmark_organizer_pro.constants import APP_VERSION, DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.utils.runtime import atomic_json_write


UPDATE_CONFIG_FILE = DATA_DIR / "update_config.json"
UPDATE_CACHE_DIR = DATA_DIR / "updates"
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
    tufup_installed: bool
    can_check: bool
    reason: str
    checked_at: str


class UpdateManager:
    """Manage local update policy without applying updates automatically."""

    def __init__(
        self,
        config_file=UPDATE_CONFIG_FILE,
        cache_dir=UPDATE_CACHE_DIR,
        current_version: str = APP_VERSION,
    ):
        self.config_file = config_file
        self.cache_dir = cache_dir
        self.current_version = current_version
        self.policy = self._load_policy()

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
        if not self.policy.enabled:
            can_check = False
            reason = "disabled"
        elif not self.policy.configured:
            can_check = False
            reason = "repository not configured"
        elif not installed:
            can_check = False
            reason = "install bookmark-organizer-pro[updates]"
        else:
            can_check = True
            reason = "ready"
        return UpdateStatus(
            policy=self.policy,
            current_version=self.current_version,
            cache_dir=str(self.cache_dir),
            tufup_installed=installed,
            can_check=can_check,
            reason=reason,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
