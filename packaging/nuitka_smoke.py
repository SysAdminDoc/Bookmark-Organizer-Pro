"""Small executable entry point for Nuitka compiler smoke tests."""

from __future__ import annotations

import sys

APP_NAME = "Bookmark Organizer Pro"
APP_VERSION = "6.6.26"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] not in ("--version", "-V"):
        print("Usage: BookmarkOrganizerProSmoke --version")
        return 2
    print(f"{APP_NAME} v{APP_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
