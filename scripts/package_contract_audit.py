"""Validate generated install inputs, release lock, and public product counts."""

from __future__ import annotations

import argparse
import hashlib
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
RELEASE_MANIFEST = ROOT / "packaging" / "release_manifest.json"
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
    release_manifest = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))
    if release_manifest.get("schema_version") != 1:
        raise ContractError("Unsupported release manifest schema")
    if tuple(release_manifest.get("user_extras", [])) != RELEASE_EXTRAS:
        raise ContractError("Release manifest user extras do not match the package contract")
    missing_extras = [name for name in RELEASE_EXTRAS if name not in extras]
    if missing_extras:
        raise ContractError("Missing release extras: " + ", ".join(missing_extras))
    expected_all = ["bookmark-organizer-pro[" + ",".join(RELEASE_EXTRAS) + "]"]
    if extras.get("all") != expected_all:
        raise ContractError(f"The all extra must aggregate exactly {expected_all[0]}")
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
    locks = release_manifest.get("locks", [])
    if not isinstance(locks, list) or not locks:
        raise ContractError("Release manifest must describe at least one lock target")
    for target in locks:
        lock_path = ROOT / str(target.get("path") or "")
        if not target.get("verified") or not lock_path.is_file():
            raise ContractError(f"Unverified or missing release lock: {lock_path.name}")
        expected_digest = str(target.get("sha256") or "").lower()
        actual_digest = hashlib.sha256(lock_path.read_bytes()).hexdigest()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_digest) or expected_digest != actual_digest:
            raise ContractError(f"Release lock digest drift: {lock_path.name}")
        if not re.fullmatch(r"3\.\d+", str(target.get("python") or "")):
            raise ContractError(f"Release lock has no explicit Python target: {lock_path.name}")
        if target.get("platform") not in {"win32", "linux", "darwin"}:
            raise ContractError(f"Release lock has no explicit platform target: {lock_path.name}")
    exclusions = release_manifest.get("unlocked_supported_environments", {})
    if not exclusions.get("python") or not exclusions.get("platforms") or not exclusions.get("install_policy"):
        raise ContractError("Release manifest must state truthful exclusions for unlocked environments")
    ownership = release_manifest.get("module_ownership", {})
    package_dirs = {
        path.name for path in (ROOT / "bookmark_organizer_pro").iterdir()
        if path.is_dir() and any(path.glob("*.py")) and path.name != "__pycache__"
    }
    if set(ownership) != package_dirs:
        raise ContractError(
            f"Module ownership drift: manifest={sorted(ownership)}, package={sorted(package_dirs)}"
        )
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
        "service_modules": len(list((ROOT / "bookmark_organizer_pro" / "services").glob("*.py"))) - 1,
        "ui_modules": len(list((ROOT / "bookmark_organizer_pro" / "ui").glob("*.py"))) - 1,
        "test_files": len(list((ROOT / "tests").glob("test_*.py"))),
    }


def validate_product_claims() -> dict[str, int]:
    expected = json.loads(CLAIMS.read_text(encoding="utf-8"))
    actual = live_product_claims()
    if expected != actual:
        raise ContractError(f"Product claim drift: expected {expected}, live {actual}")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    claim_line = (
        f"{actual['cli_subcommands']} CLI subcommands, {actual['mcp_tools']} MCP tools, "
        f"{actual['ai_providers']} AI providers, {actual['extension_surfaces']} extension surfaces, "
        f"{actual['service_modules']} service modules, {actual['ui_modules']} UI modules, "
        f"and {actual['test_files']} test files"
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
    manifest = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))
    targets = manifest.get("locks", [])
    target = next(
        (item for item in targets if item.get("path") == LOCK.relative_to(ROOT).as_posix()),
        None,
    )
    if target is None:
        raise ContractError("Release manifest has no pylock.toml target to update")
    target.update({
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "platform": sys.platform,
        "verified": True,
        "sha256": hashlib.sha256(LOCK.read_bytes()).hexdigest(),
    })
    RELEASE_MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    manifest = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))
    manifest["locks"] = [{
        "path": LOCK.relative_to(ROOT).as_posix(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "platform": sys.platform,
        "verified": True,
    }]
    RELEASE_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


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
