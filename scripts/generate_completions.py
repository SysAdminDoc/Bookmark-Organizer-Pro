#!/usr/bin/env python3
"""Generate or verify parser-derived bop shell completions."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bookmark_organizer_pro.cli_completions import (  # noqa: E402
    build_completion_model,
    render_completion_files,
)


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "completions"


def mismatched_files(output_dir: Path, rendered: dict[str, str]) -> list[Path]:
    """Return generated files that are missing or different on disk."""

    return [
        output_dir / filename
        for filename, content in rendered.items()
        if not (output_dir / filename).is_file()
        or (output_dir / filename).read_text(encoding="utf-8") != content
    ]


def write_completions(output_dir: Path, *, check: bool = False) -> list[Path]:
    """Write completions, or return drifted paths when ``check`` is true."""

    rendered = render_completion_files(build_completion_model())
    output_dir = Path(output_dir)
    if check:
        return mismatched_files(output_dir, rendered)
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in rendered.items():
        (output_dir / filename).write_text(content, encoding="utf-8", newline="\n")
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if checked-in completions do not match the CLI parser",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="completion directory (default: scripts/completions)",
    )
    args = parser.parse_args(argv)
    drift = write_completions(args.output_dir, check=args.check)
    if drift:
        for path in drift:
            print(f"completion drift: {path}", file=sys.stderr)
        return 1
    if args.check:
        print(f"completions are current in {args.output_dir}")
    else:
        print(f"generated completions in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

