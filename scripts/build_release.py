"""Build a reproducible Bookmark Organizer Pro artifact in an isolated venv."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import package_contract_audit as audit


DEFAULT_VENV = ROOT / "build" / "release-venv"
DEFAULT_WORK = ROOT / "build" / "pyinstaller"
DEFAULT_DIST = ROOT / "dist"


class ReleaseBuildError(RuntimeError):
    """Raised when the isolated release build contract cannot be satisfied."""


def venv_python(path: Path, platform: str = sys.platform) -> Path:
    scripts = "Scripts" if platform.startswith("win") else "bin"
    executable = "python.exe" if platform.startswith("win") else "python"
    return Path(path) / scripts / executable


def _run(command: Sequence[str | Path], *, env: dict[str, str] | None = None) -> None:
    subprocess.run([str(part) for part in command], cwd=ROOT, env=env, check=True)


def _is_clean_worktree() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=True
    )
    return not result.stdout.strip()


def build_release(
    *,
    venv_dir: Path = DEFAULT_VENV,
    work_dir: Path = DEFAULT_WORK,
    dist_dir: Path = DEFAULT_DIST,
    reuse_venv: bool = False,
    allow_dirty: bool = False,
    allow_unlocked_target: bool = False,
    smoke: bool = True,
) -> Path:
    """Create, package, and smoke a release using the declared profile."""
    if not allow_dirty and not _is_clean_worktree():
        raise ReleaseBuildError("release builds require a clean Git worktree")

    manifest = json.loads(audit.RELEASE_MANIFEST.read_text(encoding="utf-8"))
    lock_target = audit._matching_lock_target(manifest)
    if lock_target is None and not allow_unlocked_target:
        raise ReleaseBuildError(
            f"no verified lock for Python {sys.version_info.major}.{sys.version_info.minor} on {sys.platform}"
        )

    venv_dir = Path(venv_dir)
    if not reuse_venv and venv_dir.exists():
        shutil.rmtree(venv_dir)
    if not venv_python(venv_dir).exists():
        venv.EnvBuilder(with_pip=True, clear=False).create(venv_dir)
    python = venv_python(venv_dir)

    tools = manifest["build_tools"]
    _run([
        python, "-m", "pip", "install", "--disable-pip-version-check",
        f"pip=={tools['pip']}", f"setuptools=={tools['setuptools']}",
        f"wheel=={tools['wheel']}", f"pyinstaller=={tools['pyinstaller']}",
    ])

    if lock_target is not None:
        requirements = ROOT / "build" / "release-lock-requirements.txt"
        audit.write_locked_requirements(requirements)
        _run([
            python, "-m", "pip", "install", "--disable-pip-version-check",
            "--require-hashes", "--only-binary=:all:", "-r", requirements,
        ])
        _run([python, "-m", "pip", "install", "--no-deps", "--no-build-isolation", "."])
    else:
        _run([python, "-m", "pip", "install", ".[all]"])

    env = os.environ.copy()
    if allow_dirty:
        env["BOP_ALLOW_DIRTY_RELEASE"] = "1"
    if allow_unlocked_target:
        env["BOP_ALLOW_UNLOCKED_RELEASE"] = "1"
    metadata_dir = ROOT / "build" / "release_metadata"
    _run([python, "scripts/package_contract_audit.py", "--prepare-build-metadata", metadata_dir], env=env)
    _run([
        python, "-m", "PyInstaller", "packaging/bookmark_organizer.spec",
        "--clean", "--noconfirm", "--workpath", work_dir, "--distpath", dist_dir,
    ], env=env)

    artifact = dist_dir / ("BookmarkOrganizerPro.exe" if sys.platform.startswith("win") else "BookmarkOrganizerPro")
    if smoke:
        smoke_command: list[str | Path] = [python, "scripts/release_artifact_smoke.py", "--artifact", artifact]
        if allow_dirty:
            smoke_command.append("--allow-dirty")
        _run(smoke_command, env=env)
    return artifact


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, default=DEFAULT_VENV)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK)
    parser.add_argument("--dist-dir", type=Path, default=DEFAULT_DIST)
    parser.add_argument("--reuse-venv", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--allow-unlocked-target", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    args = parser.parse_args(argv)
    try:
        artifact = build_release(
            venv_dir=args.venv,
            work_dir=args.work_dir,
            dist_dir=args.dist_dir,
            reuse_venv=args.reuse_venv,
            allow_dirty=args.allow_dirty,
            allow_unlocked_target=args.allow_unlocked_target,
            smoke=not args.skip_smoke,
        )
    except (OSError, ReleaseBuildError, audit.ContractError, subprocess.CalledProcessError) as exc:
        print(f"release build failed: {exc}", file=sys.stderr)
        return 1
    print(artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
