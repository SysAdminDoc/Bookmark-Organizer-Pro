"""Validate generated install inputs, release lock, and public product counts."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
REQUIREMENTS = ROOT / "requirements.txt"
LOCK = ROOT / "pylock.toml"
CLAIMS = ROOT / "packaging" / "product_claims.json"
RELEASE_EXTRAS = ("ai", "encryption", "mcp", "sunvalley", "themedetect")
INSTALL_LINE = ".[" + ",".join(RELEASE_EXTRAS) + "]"


class ContractError(RuntimeError):
    """Raised when a release input or public claim has drifted."""


def _dependency_name(requirement: str) -> str:
    return re.split(r"[<>=!~ ;\[]", requirement, maxsplit=1)[0].lower().replace("_", "-")


def validate_dependency_contract() -> dict[str, int]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = data["project"]
    extras = project.get("optional-dependencies", {})
    missing_extras = [name for name in RELEASE_EXTRAS if name not in extras]
    if missing_extras:
        raise ContractError("Missing release extras: " + ", ".join(missing_extras))
    direct = list(project.get("dependencies", []))
    for extra in RELEASE_EXTRAS:
        direct.extend(extras[extra])
    unbounded = sorted({_dependency_name(item) for item in direct if ">=" not in item})
    if unbounded:
        raise ContractError("Direct dependencies missing lower bounds: " + ", ".join(unbounded))
    install_lines = [
        line.strip()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if install_lines != [INSTALL_LINE]:
        raise ContractError(f"requirements.txt must contain only {INSTALL_LINE!r}")
    if not LOCK.is_file():
        raise ContractError("requirements.lock is missing; run with --update-lock")
    lock_data = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    packages = lock_data.get("packages", [])
    if not isinstance(packages, list) or not packages:
        raise ContractError("pylock.toml does not contain a release resolution")
    unlocked = [
        item.get("name", "unknown")
        for item in packages
        if not item.get("version") and "directory" not in item
    ]
    if unlocked:
        raise ContractError("Unpinned release dependencies: " + ", ".join(unlocked[:10]))
    return {
        "direct_dependencies": len({_dependency_name(item) for item in direct}),
        "locked_dependencies": len(packages),
    }


def live_product_claims() -> dict[str, int]:
    from bookmark_organizer_pro.ai import AI_PROVIDERS
    from bookmark_organizer_pro.cli import BookmarkCLI
    from bookmark_organizer_pro.mcp_server import TOOLS

    parser = BookmarkCLI.__new__(BookmarkCLI)._build_parser()
    subcommands = next(action.choices for action in parser._actions if getattr(action, "choices", None))
    extension_surfaces = sum(
        (ROOT / "browser-extension" / name).is_file()
        for name in ("popup.html", "options.html", "sidepanel.html")
    )
    return {
        "cli_subcommands": len(subcommands),
        "mcp_tools": len(TOOLS),
        "ai_providers": len(AI_PROVIDERS),
        "extension_surfaces": extension_surfaces,
    }


def validate_product_claims() -> dict[str, int]:
    expected = json.loads(CLAIMS.read_text(encoding="utf-8"))
    actual = live_product_claims()
    if expected != actual:
        raise ContractError(f"Product claim drift: expected {expected}, live {actual}")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    claim_line = (
        f"{actual['cli_subcommands']} CLI subcommands, {actual['mcp_tools']} MCP tools, "
        f"{actual['ai_providers']} AI providers, and {actual['extension_surfaces']} extension surfaces"
    )
    if claim_line not in readme:
        raise ContractError("README executable product-count claim is stale or missing")
    return actual


def update_lock() -> None:
    command = [
        sys.executable,
        "-m",
        "pip",
        "lock",
        INSTALL_LINE,
        "--output",
        str(LOCK),
        "--quiet",
    ]
    subprocess.run(command, cwd=ROOT, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-lock", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.update_lock:
            update_lock()
        report = validate_dependency_contract()
        report.update(validate_product_claims())
    except (ContractError, OSError, subprocess.CalledProcessError) as exc:
        print(f"package contract failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
