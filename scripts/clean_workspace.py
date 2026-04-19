#!/usr/bin/env python3
"""Remove generated local artifacts from the repository workspace."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIRS = (
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    "htmlcov",
)
GENERATED_FILES = (
    ".coverage",
    "coverage.xml",
)


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT)
        return True
    except ValueError:
        return False


def _remove_path(path: Path, *, dry_run: bool) -> bool:
    if not path.exists() or not _inside_repo(path):
        return False
    if dry_run:
        print(f"would remove {path.relative_to(ROOT)}")
        return True
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    print(f"removed {path.relative_to(ROOT)}")
    return True


def clean_workspace(*, dry_run: bool = False) -> int:
    removed = 0
    for relative in GENERATED_DIRS:
        removed += int(_remove_path(ROOT / relative, dry_run=dry_run))

    for cache_dir in ROOT.rglob("__pycache__"):
        removed += int(_remove_path(cache_dir, dry_run=dry_run))

    for pattern in ("*.pyc", "*.pyo", "*.pyd"):
        for artifact in ROOT.rglob(pattern):
            removed += int(_remove_path(artifact, dry_run=dry_run))

    for relative in GENERATED_FILES:
        removed += int(_remove_path(ROOT / relative, dry_run=dry_run))

    if removed == 0:
        print("workspace already clean")
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print paths without deleting")
    args = parser.parse_args()
    clean_workspace(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
