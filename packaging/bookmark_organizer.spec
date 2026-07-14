# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Bookmark Organizer Pro

Usage:
    pyinstaller packaging/bookmark_organizer.spec --clean --noconfirm

This will create a standalone executable in the 'dist' folder.

Requirements:
    pip install pyinstaller

Options:
    --onefile: Create single executable (default)
    --windowed: No console window (default for GUI)
"""

from pathlib import Path
import json
import sys

from PyInstaller.utils.hooks import collect_all

# =============================================================================
# CONFIGURATION
# =============================================================================

APP_NAME = "Bookmark Organizer Pro"
APP_VERSION = "6.12.0"
SCRIPT_NAME = "main.py"
ICON_FILE = "bookmark_organizer.ico"
PNG_ICON_FILE = "bookmark_organizer.png"

SPEC_DIR = Path(SPECPATH).resolve()
ROOT_DIR = SPEC_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.package_contract_audit import BUILD_METADATA, prepare_build_metadata

prepare_build_metadata(BUILD_METADATA)
RELEASE_MANIFEST = json.loads((BUILD_METADATA / "release_manifest.json").read_text(encoding="utf-8"))
ASSETS_DIR = ROOT_DIR / "assets"
SCRIPT_PATH = ROOT_DIR / SCRIPT_NAME
VERSION_INFO_FILE = SPEC_DIR / "version_info.txt"
RUNTIME_HOOK_MP = SPEC_DIR / "runtime_hook_multiprocessing.py"

# =============================================================================
# ANALYSIS
# =============================================================================

# Hidden imports that PyInstaller might miss
hidden_imports = [
    'tkinter',
    'tkinter.ttk',
    'tkinter.filedialog',
    'tkinter.messagebox',
    'tkinter.simpledialog',
    'tkinter.colorchooser',
    'tkinter.font',
    'json',
    'csv',
    'hashlib',
    'html',
    'queue',
    'threading',
    'concurrent.futures',
    'urllib.parse',
    'urllib.request',
    'webbrowser',
    'tempfile',
    'shutil',
    'logging',
    'traceback',
    'dataclasses',
    'enum',
    'pathlib',
    'base64',
    'io',
    're',
    'collections',
    # Setuptools/pkg_resources runtime hook helpers
    'jaraco.text',
    'jaraco.context',
    'jaraco.functools',
    'more_itertools',
    'backports.tarfile',
    # Optional dependencies (won't fail if not installed)
    'PIL',
    'PIL.Image',
    'PIL.ImageTk',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    'bs4',
    'requests',
    'tksheet',
    'lz4.block',
    # v6.0.0 — modular backend package
    'bookmark_organizer_pro',
    'bookmark_organizer_pro.services',
    'bookmark_organizer_pro.services.ai_tools',
    'bookmark_organizer_pro.services.embeddings',
    'bookmark_organizer_pro.services.ingest',
    'bookmark_organizer_pro.services.vector_store',
    'bookmark_organizer_pro.services.hybrid_search',
    'bookmark_organizer_pro.services.encryption',
    'bookmark_organizer_pro.services.rag_chat',
    'bookmark_organizer_pro.services.citation_summarizer',
    'bookmark_organizer_pro.services.rss_feeds',
    'bookmark_organizer_pro.services.flows',
    'bookmark_organizer_pro.services.snapshot',
    'bookmark_organizer_pro.services.dead_link_scanner',
    'bookmark_organizer_pro.services.digest',
    'bookmark_organizer_pro.services.tag_linter',
    'bookmark_organizer_pro.services.dup_hybrid',
    'bookmark_organizer_pro.services.zip_export',
    'bookmark_organizer_pro.services.read_later',
    'bookmark_organizer_pro.services.nl_query',
    'bookmark_organizer_pro.services.web_tools',
    'bookmark_organizer_pro.services.api',
    'bookmark_organizer_pro.services.favicons',
    'bookmark_organizer_pro.services.icons',
    'bookmark_organizer_pro.services.local_state',
    'bookmark_organizer_pro.services.organization',
    'bookmark_organizer_pro.importers_extra',
    'bookmark_organizer_pro.io_formats',
    'bookmark_organizer_pro.io_formats.xbel',
    'bookmark_organizer_pro.cli',
    'bookmark_organizer_pro.mcp_server',
    # v6.0.0 — optional third-party (degrade gracefully if absent)
    'trafilatura',
    'fastembed',
    'lancedb',
    'cryptography',
    'mcp',
    'fastmcp',
    # AI provider SDKs (lazy-imported via ensure_package — PyInstaller misses them)
    'openai',
    'openai.resources',
    'openai.types',
    'openai.types.chat',
    'openai._streaming',
]

# Data files to include. Keep bundled runtime assets under the same
# "assets/" folder used by local development.
datas = []
binaries = []


def release_submodule_filter(name):
    """Exclude upstream command shells that require undeclared CLI-only extras."""
    return name != "mcp.cli" and not name.startswith("mcp.cli.")


for asset_name in (ICON_FILE, PNG_ICON_FILE):
    asset_path = ASSETS_DIR / asset_name
    if asset_path.exists():
        datas.append((str(asset_path), "assets"))

default_categories = ROOT_DIR / "bookmark_organizer_pro" / "core" / "default_categories.json"
if not default_categories.is_file():
    raise FileNotFoundError(f"required runtime asset is missing: {default_categories}")
datas.append((str(default_categories), "bookmark_organizer_pro/core"))

for metadata_name in ("release_manifest.json", "pylock.toml", "build_identity.json", "sbom.cdx.json"):
    metadata_path = BUILD_METADATA / metadata_name
    if not metadata_path.is_file():
        raise FileNotFoundError(f"required release metadata is missing: {metadata_path}")
    datas.append((str(metadata_path), "release"))

for capability in RELEASE_MANIFEST["runtime_capabilities"]:
    module = capability["module"]
    if module.startswith("bookmark_organizer_pro."):
        hidden_imports.append(module)
        continue
    package = module.split(".", 1)[0]
    package_datas, package_binaries, package_hidden = collect_all(
        package,
        filter_submodules=release_submodule_filter,
    )
    datas.extend(package_datas)
    binaries.extend(package_binaries)
    hidden_imports.extend(package_hidden)
    hidden_imports.append(module)

hidden_imports = sorted(set(hidden_imports))

# Packages to exclude (reduce size)
excludes = [
    'matplotlib',
    'pandas',
    'scipy',
    'pytest',
    'setuptools',
    'wheel',
    'pip',
    '_pytest',
    'doctest',
    'unittest',
]

a = Analysis(
    [str(SCRIPT_PATH)],
    pathex=[str(ROOT_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(RUNTIME_HOOK_MP)],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# =============================================================================
# PYZ (Python bytecode archive)
# =============================================================================

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=None,
)

# =============================================================================
# EXECUTABLE
# =============================================================================

icon_path = ASSETS_DIR / ICON_FILE
exe_icon = str(icon_path) if icon_path.exists() else None
version_info = (
    str(VERSION_INFO_FILE)
    if sys.platform.startswith("win") and VERSION_INFO_FILE.exists()
    else None
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='BookmarkOrganizerPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Compress with UPX if available
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window (GUI app)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=exe_icon,
    version=version_info,  # PyInstaller EXE() reads kwargs['version'] for the Windows version resource
)

# =============================================================================
# COLLECT (for --onedir mode, uncomment if needed)
# =============================================================================

# If you want a folder instead of single file, uncomment this and
# comment out the 'a.binaries, a.zipfiles, a.datas' in EXE above:

# coll = COLLECT(
#     exe,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     strip=False,
#     upx=True,
#     upx_exclude=[],
#     name='BookmarkOrganizerPro',
# )

# =============================================================================
# macOS APP BUNDLE (uncomment for macOS builds)
# =============================================================================

# app = BUNDLE(
#     exe,
#     name='Bookmark Organizer Pro.app',
#     icon='bookmark_organizer.icns',
#     bundle_identifier='com.bookmarkorganizer.pro',
#     info_plist={
#         'CFBundleName': APP_NAME,
#         'CFBundleDisplayName': APP_NAME,
#         'CFBundleVersion': APP_VERSION,
#         'CFBundleShortVersionString': APP_VERSION,
#         'NSHighResolutionCapable': True,
#         'NSRequiresAquaSystemAppearance': False,  # Support dark mode
#     },
# )
