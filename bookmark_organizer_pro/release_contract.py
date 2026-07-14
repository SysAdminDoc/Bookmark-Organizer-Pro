"""Runtime verification for frozen release artifacts.

The build embeds a small release directory containing the exact dependency
resolution, build identity, capability manifest, and CycloneDX SBOM.  This
module deliberately avoids importing the desktop UI so release smoke tests can
validate a windowed executable headlessly.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import sys
from pathlib import Path
from typing import Any

from bookmark_organizer_pro.constants import APP_VERSION


def _canonical_name(name: str) -> str:
    return name.lower().replace("_", "-")


def release_directory() -> Path:
    """Return the embedded release metadata directory."""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    embedded = bundle_root / "release"
    if embedded.is_dir():
        return embedded
    return Path(__file__).resolve().parents[1] / "build" / "release_metadata"


def _json_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def build_runtime_contract(metadata_dir: Path | None = None) -> dict[str, Any]:
    """Validate the embedded release contract and return a JSON-safe report."""
    metadata_dir = Path(metadata_dir or release_directory())
    report: dict[str, Any] = {
        "ok": False,
        "app_version": APP_VERSION,
        "release_directory": str(metadata_dir),
        "capabilities": {},
        "errors": [],
    }
    errors: list[str] = report["errors"]

    try:
        manifest = _json_file(metadata_dir / "release_manifest.json")
        identity = _json_file(metadata_dir / "build_identity.json")
        sbom = _json_file(metadata_dir / "sbom.cdx.json")
        lock_bytes = (metadata_dir / "pylock.toml").read_bytes()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"release metadata unavailable: {exc}")
        return report

    report.update({
        "commit": identity.get("commit", ""),
        "dirty": bool(identity.get("dirty", True)),
        "lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "lock_verified": bool(identity.get("lock_verified", False)),
        "release_profile": identity.get("release_profile", ""),
    })
    if identity.get("schema_version") != 1:
        errors.append("unsupported build identity schema")
    if manifest.get("schema_version") != 2:
        errors.append("unsupported release manifest schema")
    if identity.get("app_version") != APP_VERSION:
        errors.append("build identity app version does not match runtime")
    expected_lock = str(identity.get("lock_sha256") or "").lower()
    if report["lock_sha256"] != expected_lock:
        errors.append("embedded lock digest does not match build identity")

    dependency_versions = identity.get("dependency_versions", {})
    if not isinstance(dependency_versions, dict):
        dependency_versions = {}
        errors.append("build identity dependency versions are invalid")

    capabilities = manifest.get("runtime_capabilities", [])
    if not isinstance(capabilities, list) or not capabilities:
        errors.append("release manifest has no runtime capabilities")
        capabilities = []
    for capability in capabilities:
        if not isinstance(capability, dict):
            errors.append("invalid runtime capability entry")
            continue
        name = str(capability.get("name") or "unnamed")
        module = str(capability.get("module") or "")
        distribution = str(capability.get("distribution") or "")
        state: dict[str, Any] = {"module": module, "available": False}
        try:
            imported = importlib.import_module(module)
            state["available"] = True
            if distribution:
                actual = importlib.metadata.version(distribution)
                expected = str(dependency_versions.get(_canonical_name(distribution)) or "")
                state.update({"distribution": distribution, "version": actual, "expected": expected})
                if not expected or actual != expected:
                    raise RuntimeError(f"version {actual!r} does not match build identity {expected!r}")
            if name == "default_categories":
                categories = getattr(imported, "DEFAULT_CATEGORIES", {})
                category_count = len(categories) if isinstance(categories, dict) else 0
                pattern_count = sum(len(patterns) for patterns in categories.values()) if category_count else 0
                state.update({"categories": category_count, "patterns": pattern_count})
                if category_count < int(capability.get("minimum_categories", 1)):
                    raise RuntimeError("bundled default categories are missing")
                if pattern_count < int(capability.get("minimum_patterns", 1)):
                    raise RuntimeError("bundled default category patterns are incomplete")
        except Exception as exc:  # pragma: no cover - exact loader failures are platform-specific
            state["error"] = str(exc)
            errors.append(f"capability {name} failed: {exc}")
        report["capabilities"][name] = state

    components = sbom.get("components", [])
    sbom_versions = {
        str(component.get("name")): str(component.get("version"))
        for component in components
        if isinstance(component, dict) and component.get("name") and component.get("version")
    }
    if sbom.get("bomFormat") != "CycloneDX" or sbom.get("specVersion") != "1.6":
        errors.append("embedded SBOM is not CycloneDX 1.6")
    if sbom_versions != {str(name): str(version) for name, version in dependency_versions.items()}:
        errors.append("embedded SBOM does not match the build dependency identity")
    report["sbom_components"] = len(sbom_versions)
    report["ok"] = not errors
    return report


def write_runtime_contract(output: Path, metadata_dir: Path | None = None) -> dict[str, Any]:
    """Write the runtime report atomically for windowed executable smokes."""
    report = build_runtime_contract(metadata_dir)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    return report
