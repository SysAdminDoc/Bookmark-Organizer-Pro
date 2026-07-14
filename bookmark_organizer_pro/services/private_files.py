"""Fail-closed atomic persistence for credential-bearing local files."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


RECOVERY_GUIDANCE = (
    "Credential was not published. Use the OS keyring, or restore owner-only "
    "file-permission support and retry."
)


class PrivateFilePermissionError(PermissionError):
    """Raised when owner-only permissions cannot be guaranteed."""


def _platform_name() -> str:
    return os.name


def restrict_private_file(path: str | Path) -> None:
    """Require owner-only access for an existing file or raise."""

    path = Path(path)
    if _platform_name() != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError as exc:
            raise PrivateFilePermissionError(f"Could not restrict {path.name}. {RECOVERY_GUIDANCE}") from exc
        return
    username = os.environ.get("USERNAME", "").strip()
    if not username:
        raise PrivateFilePermissionError(
            f"Windows user identity is unavailable for {path.name}. {RECOVERY_GUIDANCE}"
        )
    try:
        completed = subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"{username}:(F)",
            ],
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PrivateFilePermissionError(
            f"Windows ACL hardening is unavailable for {path.name}. {RECOVERY_GUIDANCE}"
        ) from exc
    if completed.returncode != 0:
        raise PrivateFilePermissionError(
            f"Windows ACL hardening failed for {path.name}. {RECOVERY_GUIDANCE}"
        )


def atomic_write_private_bytes(path: str | Path, payload: bytes) -> None:
    """Publish bytes only after their temporary file is owner-only and durable."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        if _platform_name() != "nt":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        restrict_private_file(temporary)
        os.replace(temporary, path)
        if _platform_name() != "nt":
            parent_descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(parent_descriptor)
            finally:
                os.close(parent_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def atomic_write_private_text(path: str | Path, payload: str) -> None:
    atomic_write_private_bytes(path, payload.encode("utf-8"))


def atomic_copy_private_file(source: str | Path, destination: str | Path) -> None:
    atomic_write_private_bytes(destination, Path(source).read_bytes())
