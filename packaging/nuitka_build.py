"""Build Bookmark Organizer Pro with Nuitka."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List


ROOT_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT_DIR / "assets"
MAIN_SCRIPT = ROOT_DIR / "main.py"
SMOKE_SCRIPT = ROOT_DIR / "packaging" / "nuitka_smoke.py"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "dist" / "nuitka"
DEFAULT_JOBS = 4
APP_NAME = "Bookmark Organizer Pro"
EXE_NAME = "BookmarkOrganizerPro"
SMOKE_EXE_NAME = "BookmarkOrganizerProSmoke"
COMPANY_NAME = "Bookmark Organizer Team"
FILE_DESCRIPTION = "Bookmark Organizer Pro - Ultimate Bookmark Management"


def _app_version() -> str:
    sys.path.insert(0, str(ROOT_DIR))
    from bookmark_organizer_pro.constants import APP_VERSION
    return APP_VERSION


def _file_version(version: str) -> str:
    parts = version.split(".")
    return ".".join((*parts, "0")[:4])


def _asset_args(root: Path = ROOT_DIR) -> List[str]:
    assets = root / "assets"
    args: List[str] = []
    for name in ("bookmark_organizer.ico", "bookmark_organizer.png"):
        source = assets / name
        if source.exists():
            args.append(f"--include-data-files={source}=assets/{name}")
    return args


def build_command(
    *,
    mode: str = "onefile",
    target: str = "app",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    python_executable: str = sys.executable,
    version: str | None = None,
    root: Path = ROOT_DIR,
    jobs: int = DEFAULT_JOBS,
) -> List[str]:
    version = version or _app_version()
    output_dir = Path(output_dir)
    icon_path = root / "assets" / "bookmark_organizer.ico"
    report_path = output_dir / "compilation-report.xml"
    is_smoke = target == "smoke"
    entrypoint = SMOKE_SCRIPT if is_smoke else MAIN_SCRIPT
    output_filename = SMOKE_EXE_NAME if is_smoke else EXE_NAME
    command = [
        python_executable,
        "-m",
        "nuitka",
        f"--mode={mode}",
        "--assume-yes-for-downloads",
        f"--output-dir={output_dir}",
        f"--output-filename={output_filename}",
        f"--report={report_path}",
        f"--jobs={jobs}",
        f"--product-name={APP_NAME}",
        f"--file-description={FILE_DESCRIPTION}",
        f"--file-version={_file_version(version)}",
        f"--product-version={_file_version(version)}",
        f"--company-name={COMPANY_NAME}",
    ]
    if not is_smoke:
        command.extend(("--enable-plugin=tk-inter", "--include-package=bookmark_organizer_pro"))
    if sys.platform.startswith("win"):
        console_mode = "force" if is_smoke else "disable"
        command.append(f"--windows-console-mode={console_mode}")
        if icon_path.exists():
            command.append(f"--windows-icon-from-ico={icon_path}")
    command.extend(_asset_args(root))
    command.append(str(entrypoint))
    return command


def quote_command(parts: Iterable[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Bookmark Organizer Pro with Nuitka")
    parser.add_argument("--mode", choices=("onefile", "standalone"), default="onefile")
    parser.add_argument("--target", choices=("app", "smoke"), default="app")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help="Parallel compiler jobs")
    parser.add_argument("--dry-run", action="store_true", help="Print the Nuitka command without running it")
    args = parser.parse_args(argv)

    command = build_command(
        mode=args.mode,
        target=args.target,
        output_dir=args.output_dir,
        jobs=max(1, args.jobs),
    )
    if args.dry_run:
        print(quote_command(command))
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    return subprocess.call(command, cwd=ROOT_DIR)


if __name__ == "__main__":
    raise SystemExit(main())
