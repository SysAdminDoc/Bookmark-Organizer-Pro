# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Bookmark Organizer Pro

Usage:
    pyinstaller bookmark_organizer.spec

This will create a standalone executable in the 'dist' folder.

Requirements:
    pip install pyinstaller

Options:
    --onefile: Create single executable (default)
    --windowed: No console window (default for GUI)
"""

import sys
import os
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================

APP_NAME = "Bookmark Organizer Pro"
APP_VERSION = "4.1.0"
SCRIPT_NAME = "bookmark_organizer_pro_v4.py"
ICON_FILE = "bookmark_organizer.ico"

# Determine the base path
BASE_PATH = Path(SPEC).parent if 'SPEC' in dir() else Path('.')
SCRIPT_PATH = BASE_PATH / SCRIPT_NAME

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
    # Optional dependencies (won't fail if not installed)
    'PIL',
    'PIL.Image',
    'PIL.ImageTk',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    'bs4',
    'requests',
    'pystray',
]

# Data files to include
datas = [
    # Include icon file if it exists
]

# Check for icon file
icon_path = BASE_PATH / ICON_FILE
if icon_path.exists():
    datas.append((str(icon_path), '.'))

# Binary files to include
binaries = []

# Packages to exclude (reduce size)
excludes = [
    'matplotlib',
    'numpy',
    'pandas',
    'scipy',
    'pytest',
    'setuptools',
    'wheel',
    'pip',
    '_pytest',
    'doctest',
    'pydoc',
    'unittest',
]

a = Analysis(
    [str(SCRIPT_PATH)],
    pathex=[str(BASE_PATH)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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

# Icon path for executable
exe_icon = str(icon_path) if icon_path.exists() else None

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
    # Version info (Windows)
    version_info=None,  # Can add version_info.txt file
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
