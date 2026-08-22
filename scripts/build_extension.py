#!/usr/bin/env python3
"""Build deterministic Chromium and Firefox browser-extension artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bookmark_organizer_pro.constants import APP_VERSION


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


# Firefox data collection consent vocabulary. Mozilla requires every extension to
# declare what it collects or transmits; "none" is the explicit no-collection value
# and "technicalAndInteraction" may only ever be optional.
DATA_COLLECTION_TYPES = frozenset({
    "authenticationInfo", "bookmarksInfo", "browsingActivity",
    "financialAndPaymentInfo", "healthInfo", "locationInfo",
    "personalCommunications", "personallyIdentifyingInfo", "searchTerms",
    "websiteActivity", "websiteContent",
})
OPTIONAL_ONLY_DATA_COLLECTION_TYPES = frozenset({"technicalAndInteraction"})


def validate_data_collection_permissions(declared) -> None:
    """Validate the Gecko data_collection_permissions disclosure block."""
    if not isinstance(declared, dict):
        raise ValueError(
            "Firefox build requires gecko.data_collection_permissions; declare the data "
            "the extension transmits, or ['none'] when it transmits nothing"
        )
    required = declared.get("required")
    if not isinstance(required, list) or not required:
        raise ValueError("Firefox data_collection_permissions.required must be a non-empty list")
    optional = declared.get("optional", [])
    if not isinstance(optional, list):
        raise ValueError("Firefox data_collection_permissions.optional must be a list")
    if "none" in required and len(required) > 1:
        raise ValueError("Firefox data_collection_permissions.required cannot combine 'none' with data types")
    if "none" in optional:
        raise ValueError("Firefox data_collection_permissions.optional cannot declare 'none'")
    for value in required:
        if value == "none":
            continue
        if value in OPTIONAL_ONLY_DATA_COLLECTION_TYPES:
            raise ValueError(f"Firefox data collection type {value!r} must be optional, not required")
        if value not in DATA_COLLECTION_TYPES:
            raise ValueError(f"Unknown Firefox data collection type {value!r}")
    for value in optional:
        if value not in DATA_COLLECTION_TYPES | OPTIONAL_ONLY_DATA_COLLECTION_TYPES:
            raise ValueError(f"Unknown Firefox data collection type {value!r}")
    if set(required) & set(optional):
        raise ValueError("Firefox data collection types cannot be both required and optional")


# Firefox understands browser_specific_settings.gecko.data_collection_permissions
# from 140, and Firefox for Android from 142. Declaring the key under a lower
# floor is what web-ext reports as KEY_FIREFOX_UNSUPPORTED_BY_MIN_VERSION, and
# it means the users on those older builds get a manifest key their browser
# does not read.
DATA_COLLECTION_MIN_DESKTOP = (140, 0)
DATA_COLLECTION_MIN_ANDROID = (142, 0)


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for chunk in str(value or "").split("."):
        digits = "".join(character for character in chunk if character.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def validate_data_collection_floors(settings) -> None:
    """Both Gecko floors must be new enough for the disclosure key."""
    desktop = settings.get("gecko", {}).get("strict_min_version")
    if _version_tuple(desktop) < DATA_COLLECTION_MIN_DESKTOP:
        raise ValueError(
            f"Firefox strict_min_version {desktop!r} predates "
            f"{'.'.join(str(part) for part in DATA_COLLECTION_MIN_DESKTOP)}, which "
            "introduced data_collection_permissions"
        )
    android = settings.get("gecko_android", {}).get("strict_min_version")
    if not android:
        raise ValueError(
            "Firefox build requires browser_specific_settings.gecko_android."
            "strict_min_version; Android reads the disclosure key only from 142"
        )
    if _version_tuple(android) < DATA_COLLECTION_MIN_ANDROID:
        raise ValueError(
            f"Firefox for Android strict_min_version {android!r} predates "
            f"{'.'.join(str(part) for part in DATA_COLLECTION_MIN_ANDROID)}"
        )


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
        settings = manifest.get("browser_specific_settings", {})
        gecko = settings.get("gecko", {})
        if not gecko.get("id") or not gecko.get("strict_min_version"):
            raise ValueError("Firefox build requires a stable Gecko ID and minimum version")
        validate_data_collection_permissions(gecko.get("data_collection_permissions"))
        validate_data_collection_floors(settings)


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
