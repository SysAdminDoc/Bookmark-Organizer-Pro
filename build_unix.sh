#!/bin/bash
# Build script for macOS/Linux
# Usage: ./build_unix.sh

set -e

echo "============================================"
echo "Bookmark Organizer Pro - Unix Build"
echo "============================================"

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 not found"
    exit 1
fi

# Check for PyInstaller
if ! python3 -c "import PyInstaller" 2>/dev/null; then
    echo "Installing PyInstaller..."
    pip3 install pyinstaller
fi

# Install dependencies
echo ""
echo "Checking dependencies..."
pip3 install beautifulsoup4 requests Pillow pystray --quiet 2>/dev/null || true

# Build
echo ""
echo "Building executable..."
pyinstaller bookmark_organizer.spec --clean

echo ""
echo "============================================"
echo "BUILD SUCCESSFUL"
echo "============================================"
echo "Executable: dist/BookmarkOrganizerPro"
echo ""

# macOS: Create app bundle
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Note: For macOS app bundle, edit spec file to enable BUNDLE section"
fi
