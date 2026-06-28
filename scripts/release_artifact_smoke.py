"""Smoke-test the locally built Bookmark Organizer Pro distributable."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ReleaseArtifactSmokeError(AssertionError):
    """Raised when the built release artifact fails the local smoke contract."""


@dataclass(frozen=True)
class SmokeResult:
    artifact: Path
    stdout: str
    stderr: str
    returncode: int


def default_artifact(root: Path = ROOT, platform: str = sys.platform) -> Path:
    name = "BookmarkOrganizerPro.exe" if platform.startswith("win") else "BookmarkOrganizerPro"
    return root / "dist" / name


def check_artifact_file(path: Path) -> None:
    if not path.exists():
        raise ReleaseArtifactSmokeError(f"artifact does not exist: {path}")
    if not path.is_file():
        raise ReleaseArtifactSmokeError(f"artifact is not a file: {path}")
    if path.stat().st_size < 1_000_000:
        raise ReleaseArtifactSmokeError(f"artifact is unexpectedly small: {path.stat().st_size} bytes")


def has_lingering_windows_process(process_name: str) -> bool:
    if not sys.platform.startswith("win"):
        return False
    completed = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/NH"],
        text=True,
        capture_output=True,
        check=False,
    )
    return process_name.lower() in (completed.stdout or "").lower()


def smoke_artifact(
    artifact: Path,
    *,
    expected_version: str,
    timeout: int = 120,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> SmokeResult:
    artifact = artifact.resolve()
    check_artifact_file(artifact)
    completed = runner(
        [str(artifact), "--version"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    expected = f"Bookmark Organizer Pro v{expected_version}"
    if completed.returncode != 0:
        raise ReleaseArtifactSmokeError(f"{artifact.name} --version exited {completed.returncode}: {stderr}")
    if expected not in stdout:
        raise ReleaseArtifactSmokeError(f"{artifact.name} reported unexpected version output: {stdout!r}")
    time.sleep(1)
    if has_lingering_windows_process(artifact.name):
        raise ReleaseArtifactSmokeError(f"{artifact.name} left a running process after --version")
    return SmokeResult(artifact=artifact, stdout=stdout, stderr=stderr, returncode=completed.returncode)


def main(argv: Sequence[str] | None = None) -> int:
    from bookmark_organizer_pro.constants import APP_VERSION

    parser = argparse.ArgumentParser(description="Smoke-test the locally built release artifact.")
    parser.add_argument("--artifact", type=Path, default=default_artifact(), help="artifact path to execute")
    parser.add_argument("--version", default=APP_VERSION, help="expected application version")
    parser.add_argument("--timeout", type=int, default=120, help="artifact execution timeout in seconds")
    args = parser.parse_args(argv)

    try:
        result = smoke_artifact(args.artifact, expected_version=args.version, timeout=args.timeout)
    except ReleaseArtifactSmokeError as exc:
        print(f"release artifact smoke failed: {exc}", file=sys.stderr)
        return 1

    print(f"{result.artifact.name}: {result.stdout}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
