"""Validate generated install inputs, release lock, and public product counts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
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
BUILD_METADATA = ROOT / "build" / "release_metadata"
RELEASE_EXTRAS = ("ai", "encryption", "mcp", "sunvalley", "themedetect")
INSTALL_LINE = ".[" + ",".join(RELEASE_EXTRAS) + "]"


class ContractError(RuntimeError):
    """Raised when a release input or public claim has drifted."""


def _dependency_name(requirement: str) -> str:
    return re.split(r"[<>=!~ ;\[]", requirement, maxsplit=1)[0].lower().replace("_", "-")


def _lock_data() -> dict:
    return tomllib.loads(LOCK.read_text(encoding="utf-8"))


def locked_versions(lock_data: dict | None = None) -> dict[str, str]:
    """Return canonical package/version pairs from the release lock."""
    lock_data = lock_data or _lock_data()
    return {
        _dependency_name(str(item["name"])): str(item["version"])
        for item in lock_data.get("packages", [])
        if item.get("version")
    }


def validate_dependency_contract() -> dict[str, int]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = data["project"]
    extras = project.get("optional-dependencies", {})
    release_manifest = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))
    if release_manifest.get("schema_version") != 2:
        raise ContractError("Unsupported release manifest schema")
    if release_manifest.get("release_profile") != "all":
        raise ContractError("Release manifest must select the aggregate all profile")
    build_tools = release_manifest.get("build_tools", {})
    if set(build_tools) != {"pip", "setuptools", "wheel", "pyinstaller"}:
        raise ContractError("Release manifest must pin pip, setuptools, wheel, and PyInstaller")
    if not all(re.fullmatch(r"\d+(?:\.\d+)+", str(version)) for version in build_tools.values()):
        raise ContractError("Release build tools must use exact versions")
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
    lock_data = _lock_data()
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
    resolved_versions = locked_versions(lock_data)
    capabilities = release_manifest.get("runtime_capabilities", [])
    if not isinstance(capabilities, list) or not capabilities:
        raise ContractError("Release manifest must define runtime capabilities")
    capability_names: set[str] = set()
    for capability in capabilities:
        if not isinstance(capability, dict) or not capability.get("name") or not capability.get("module"):
            raise ContractError("Invalid runtime capability entry")
        name = str(capability["name"])
        if name in capability_names:
            raise ContractError(f"Duplicate runtime capability: {name}")
        capability_names.add(name)
        distribution = capability.get("distribution")
        if distribution and _dependency_name(str(distribution)) not in resolved_versions:
            raise ContractError(f"Capability dependency missing from release lock: {distribution}")
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


def _hashes_for_package(package: dict) -> list[str]:
    hashes: list[str] = []
    archives = list(package.get("wheels", []))
    if package.get("sdist"):
        archives.append(package["sdist"])
    for archive in archives:
        digest = str(archive.get("hashes", {}).get("sha256") or "").lower()
        if re.fullmatch(r"[0-9a-f]{64}", digest):
            hashes.append(digest)
    return sorted(set(hashes))


def locked_requirements_text(lock_data: dict | None = None) -> str:
    """Render a pip --require-hashes input from the standard release lock."""
    lock_data = lock_data or _lock_data()
    lines: list[str] = []
    for package in sorted(lock_data.get("packages", []), key=lambda item: str(item.get("name", ""))):
        if not package.get("version"):
            continue
        hashes = _hashes_for_package(package)
        if not hashes:
            raise ContractError(f"Locked package has no SHA-256 archive hash: {package.get('name')}")
        requirement = f"{package['name']}=={package['version']}"
        lines.append(requirement + " " + " ".join(f"--hash=sha256:{digest}" for digest in hashes))
    if not lines:
        raise ContractError("Release lock produced no installable requirements")
    return "\n".join(lines) + "\n"


def write_locked_requirements(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(locked_requirements_text(), encoding="utf-8")
    return path


def _installed_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _matching_lock_target(manifest: dict) -> dict | None:
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    return next(
        (
            target for target in manifest.get("locks", [])
            if target.get("verified") and target.get("python") == version and target.get("platform") == sys.platform
        ),
        None,
    )


def _git_identity() -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True
    ).stdout.strip()
    dirty = bool(subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=True
    ).stdout.strip())
    return commit, dirty


def _cyclonedx_sbom(versions: dict[str, str], lock_data: dict, identity: dict) -> dict:
    packages = {_dependency_name(str(item.get("name", ""))): item for item in lock_data.get("packages", [])}
    components = []
    for name, version in sorted(versions.items()):
        component = {
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:pypi/{name}@{version}",
        }
        hashes = _hashes_for_package(packages.get(name, {}))
        if hashes:
            component["hashes"] = [{"alg": "SHA-256", "content": digest} for digest in hashes]
        components.append(component)
    serial_seed = hashlib.sha256(
        (identity["commit"] + identity["lock_sha256"] + identity["app_version"]).encode("utf-8")
    ).hexdigest()
    serial = f"urn:uuid:{serial_seed[:8]}-{serial_seed[8:12]}-{serial_seed[12:16]}-{serial_seed[16:20]}-{serial_seed[20:32]}"
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": serial,
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "bookmark-organizer-pro",
                "version": identity["app_version"],
                "properties": [
                    {"name": "bop:commit", "value": identity["commit"]},
                    {"name": "bop:lock-sha256", "value": identity["lock_sha256"]},
                    {"name": "bop:release-profile", "value": identity["release_profile"]},
                ],
            }
        },
        "components": components,
    }


def prepare_build_metadata(output_dir: Path = BUILD_METADATA) -> dict:
    """Verify the build environment and emit deterministic embedded metadata."""
    validate_dependency_contract()
    manifest = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))
    lock_data = _lock_data()
    target = _matching_lock_target(manifest)
    allow_unlocked = os.environ.get("BOP_ALLOW_UNLOCKED_RELEASE") == "1"
    if target is None and not allow_unlocked:
        raise ContractError(
            f"No verified release lock for Python {sys.version_info.major}.{sys.version_info.minor} on {sys.platform}"
        )

    expected_versions = locked_versions(lock_data)
    if target is not None:
        drift = []
        for name, expected in expected_versions.items():
            actual = _installed_version(name)
            if actual != expected:
                drift.append(f"{name}={actual or 'missing'} (expected {expected})")
        if drift:
            raise ContractError("Build environment does not match release lock: " + ", ".join(drift[:12]))
        dependency_versions = expected_versions
    else:
        dependency_versions = {}
        for capability in manifest["runtime_capabilities"]:
            distribution = capability.get("distribution")
            if distribution:
                actual = _installed_version(str(distribution))
                if not actual:
                    raise ContractError(f"Unlocked release capability is missing: {distribution}")
                dependency_versions[_dependency_name(str(distribution))] = actual

    for tool, expected in manifest["build_tools"].items():
        actual = _installed_version(tool)
        if actual != expected:
            raise ContractError(f"Build tool {tool}={actual or 'missing'} does not match {expected}")

    from bookmark_organizer_pro.constants import APP_VERSION

    commit, dirty = _git_identity()
    if dirty and os.environ.get("BOP_ALLOW_DIRTY_RELEASE") != "1":
        raise ContractError("Release builds require a clean Git worktree")
    identity = {
        "schema_version": 1,
        "app_version": APP_VERSION,
        "commit": commit,
        "dirty": dirty,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": sys.platform,
        "release_profile": manifest["release_profile"],
        "lock_sha256": hashlib.sha256(LOCK.read_bytes()).hexdigest(),
        "lock_verified": target is not None,
        "dependency_versions": dict(sorted(dependency_versions.items())),
        "build_tools": manifest["build_tools"],
    }
    sbom = _cyclonedx_sbom(dependency_versions, lock_data, identity)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(RELEASE_MANIFEST, output_dir / "release_manifest.json")
    shutil.copyfile(LOCK, output_dir / "pylock.toml")
    (output_dir / "build_identity.json").write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "sbom.cdx.json").write_text(
        json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return identity


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
    # ``pip lock`` follows the host's native newline convention. Git stores the
    # lock as LF, so normalize before recording the byte-for-byte release digest.
    lock_bytes = LOCK.read_bytes().replace(b"\r\n", b"\n")
    LOCK.write_bytes(lock_bytes)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-lock", action="store_true")
    parser.add_argument("--prepare-build-metadata", type=Path)
    parser.add_argument("--write-locked-requirements", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.update_lock:
            update_lock()
        report = validate_dependency_contract()
        report.update(validate_product_claims())
        if args.write_locked_requirements:
            report["locked_requirements"] = str(write_locked_requirements(args.write_locked_requirements))
        if args.prepare_build_metadata:
            identity = prepare_build_metadata(args.prepare_build_metadata)
            report["build_commit"] = identity["commit"]
    except (ContractError, OSError, subprocess.CalledProcessError) as exc:
        print(f"package contract failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
