#!/usr/bin/env python3
"""Build deterministic Chromium and Firefox browser-extension artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from bookmark_organizer_pro.constants import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "browser-extension"
DEFAULT_OUTPUT = ROOT / "build" / "browser-extension"
TARGETS = {"chromium", "firefox"}
MANIFESTS = {
    "chromium": SOURCE_DIR / "manifest.json",
    "firefox": SOURCE_DIR / "manifest.firefox.json",
}
EXCLUDED_NAMES = {"manifest.json", "manifest.firefox.json"}
REQUIRED_FILES = {
    "background.js",
    "categories.json",
    "credential-vault.js",
    "i18n.js",
    "options.html",
    "options.js",
    "popup.css",
    "popup.html",
    "popup.js",
    "shared.js",
    "sidepanel.html",
    "sidepanel.js",
}


def load_manifest(target: str) -> dict:
    if target not in TARGETS:
        raise ValueError(f"Unsupported extension target: {target}")
    return json.loads(MANIFESTS[target].read_text(encoding="utf-8"))


def validate_manifest(target: str, manifest: dict) -> None:
    if manifest.get("manifest_version") != 3:
        raise ValueError(f"{target} manifest must use Manifest V3")
    if manifest.get("version") != APP_VERSION:
        raise ValueError(
            f"{target} manifest version {manifest.get('version')!r} != app {APP_VERSION}"
        )
    for key in ("name", "description", "action", "background", "permissions", "host_permissions"):
        if not manifest.get(key):
            raise ValueError(f"{target} manifest is missing {key}")
    permissions = set(manifest["permissions"])
    common = {"activeTab", "scripting", "storage", "contextMenus"}
    if not common.issubset(permissions):
        raise ValueError(f"{target} manifest is missing common permissions")
    if manifest["action"].get("default_popup") != "popup.html":
        raise ValueError(f"{target} popup must use popup.html")
    if target == "chromium":
        if manifest["background"].get("service_worker") != "background.js":
            raise ValueError("Chromium build requires the background service worker")
        if manifest.get("side_panel", {}).get("default_path") != "sidepanel.html":
            raise ValueError("Chromium build requires side_panel")
        if not {"sidePanel", "readingList"}.issubset(permissions):
            raise ValueError("Chromium build requires Side Panel and Reading List permissions")
    else:
        if manifest["background"].get("scripts") != [
            "i18n.js", "shared.js", "credential-vault.js", "background.js"
        ]:
            raise ValueError("Firefox build requires ordered background scripts")
        if manifest.get("sidebar_action", {}).get("default_panel") != "sidepanel.html":
            raise ValueError("Firefox build requires sidebar_action")
        if {"sidePanel", "readingList"} & permissions or "side_panel" in manifest:
            raise ValueError("Firefox build contains Chromium-only APIs")
        gecko = manifest.get("browser_specific_settings", {}).get("gecko", {})
        if not gecko.get("id") or not gecko.get("strict_min_version"):
            raise ValueError("Firefox build requires a stable Gecko ID and minimum version")


def validate_parity(chromium: dict, firefox: dict) -> None:
    for key in ("manifest_version", "name", "description", "default_locale", "version", "icons", "action", "commands"):
        if chromium.get(key) != firefox.get(key):
            raise ValueError(f"Extension manifests disagree on shared field {key}")
    if set(chromium.get("host_permissions", [])) != set(firefox.get("host_permissions", [])):
        raise ValueError("Extension manifests disagree on local API hosts")


def _source_files() -> list[Path]:
    files = [
        path for path in SOURCE_DIR.rglob("*")
        if path.is_file() and path.name not in EXCLUDED_NAMES and not path.name.startswith(".")
    ]
    relative = {path.relative_to(SOURCE_DIR).as_posix() for path in files}
    missing = REQUIRED_FILES - relative
    if missing:
        raise ValueError(f"Extension source is missing: {', '.join(sorted(missing))}")
    return sorted(files, key=lambda path: path.relative_to(SOURCE_DIR).as_posix())


def _safe_output(output_root: Path, target: str) -> Path:
    output_root = output_root.resolve()
    target_dir = (output_root / target).resolve()
    if target_dir.parent != output_root or output_root == ROOT:
        raise ValueError("Extension output must be a dedicated child directory")
    return target_dir


def _write_deterministic_zip(source_dir: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source_dir).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def build_target(target: str, output_root: Path = DEFAULT_OUTPUT) -> dict[str, str | int]:
    chromium = load_manifest("chromium")
    firefox = load_manifest("firefox")
    validate_manifest("chromium", chromium)
    validate_manifest("firefox", firefox)
    validate_parity(chromium, firefox)
    manifest = chromium if target == "chromium" else firefox
    target_dir = _safe_output(Path(output_root), target)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True)
    for source in _source_files():
        relative = source.relative_to(SOURCE_DIR)
        destination = target_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    (target_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    extension = ".xpi" if target == "firefox" else ".zip"
    archive = Path(output_root).resolve() / f"bookmark-organizer-pro-{target}-{APP_VERSION}{extension}"
    _write_deterministic_zip(target_dir, archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    return {
        "target": target,
        "version": APP_VERSION,
        "directory": str(target_dir),
        "archive": str(archive),
        "sha256": digest,
        "files": sum(path.is_file() for path in target_dir.rglob("*")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=["chromium", "firefox", "all"])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    targets = sorted(TARGETS) if args.target == "all" else [args.target]
    reports = [build_target(target, args.output) for target in targets]
    print(json.dumps({"artifacts": reports}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
