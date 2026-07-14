"""Smoke-test the locally built Bookmark Organizer Pro distributable."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
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
    contract: dict


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
    allow_dirty: bool = False,
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

    with tempfile.TemporaryDirectory(prefix="bop-release-contract-") as tmp:
        contract_path = Path(tmp) / "contract.json"
        contract_completed = runner(
            [str(artifact), "--release-contract", "--release-contract-output", str(contract_path)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        contract_stdout = (contract_completed.stdout or "").strip()
        contract_stderr = (contract_completed.stderr or "").strip()
        if contract_completed.returncode != 0:
            raise ReleaseArtifactSmokeError(
                f"{artifact.name} release contract exited {contract_completed.returncode}: {contract_stderr}"
            )
        try:
            payload = contract_path.read_text(encoding="utf-8") if contract_path.is_file() else contract_stdout
            contract = json.loads(payload)
        except (OSError, json.JSONDecodeError) as exc:
            raise ReleaseArtifactSmokeError(f"{artifact.name} returned invalid release contract: {exc}") from exc
    if not isinstance(contract, dict) or not contract.get("ok"):
        raise ReleaseArtifactSmokeError(f"{artifact.name} release contract failed: {contract.get('errors', [])}")
    if contract.get("app_version") != expected_version:
        raise ReleaseArtifactSmokeError("release contract version does not match the expected artifact version")
    if contract.get("release_profile") != "all":
        raise ReleaseArtifactSmokeError("release artifact was not built from the all profile")
    if contract.get("dirty") and not allow_dirty:
        raise ReleaseArtifactSmokeError("release artifact was built from a dirty worktree")
    categories = contract.get("capabilities", {}).get("default_categories", {})
    if categories.get("categories", 0) < 48 or categories.get("patterns", 0) < 7500:
        raise ReleaseArtifactSmokeError("release artifact default category asset is incomplete")
    if contract.get("sbom_components", 0) < 1:
        raise ReleaseArtifactSmokeError("release artifact has no embedded SBOM components")
    time.sleep(1)
    if has_lingering_windows_process(artifact.name):
        raise ReleaseArtifactSmokeError(f"{artifact.name} left a running process after release-contract smoke")
    return SmokeResult(
        artifact=artifact,
        stdout=stdout,
        stderr="\n".join(part for part in (stderr, contract_stderr) if part),
        returncode=completed.returncode,
        contract=contract,
    )


def main(argv: Sequence[str] | None = None) -> int:
    from bookmark_organizer_pro.constants import APP_VERSION

    parser = argparse.ArgumentParser(description="Smoke-test the locally built release artifact.")
    parser.add_argument("--artifact", type=Path, default=default_artifact(), help="artifact path to execute")
    parser.add_argument("--version", default=APP_VERSION, help="expected application version")
    parser.add_argument("--timeout", type=int, default=120, help="artifact execution timeout in seconds")
    parser.add_argument("--allow-dirty", action="store_true", help="allow a development artifact built from dirty source")
    args = parser.parse_args(argv)

    try:
        result = smoke_artifact(
            args.artifact,
            expected_version=args.version,
            timeout=args.timeout,
            allow_dirty=args.allow_dirty,
        )
    except ReleaseArtifactSmokeError as exc:
        print(f"release artifact smoke failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"{result.artifact.name}: {result.stdout}; "
        f"commit={result.contract.get('commit')} sbom={result.contract.get('sbom_components')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
