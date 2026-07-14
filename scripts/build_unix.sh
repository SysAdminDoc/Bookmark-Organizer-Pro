#!/bin/bash
# Build script for macOS/Linux
# Usage: ./scripts/build_unix.sh

set -e
cd "$(dirname "$0")/.."

echo "============================================"
echo "Bookmark Organizer Pro - Unix Build"
echo "============================================"

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 not found"
    exit 1
fi

# The checked-in lock targets Windows/Python 3.11. Unix builds resolve the same
# bounded `all` profile and record lock_verified=false in their identity.
echo ""
echo "Building executable..."
python3 scripts/build_release.py --allow-unlocked-target

echo ""
echo "============================================"
echo "BUILD SUCCESSFUL"
echo "============================================"
echo "Executable: dist/BookmarkOrganizerPro"
echo ""

# macOS: Create app bundle
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Note: For macOS app bundle, edit packaging/bookmark_organizer.spec to enable BUNDLE section"
fi
