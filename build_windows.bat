@echo off
REM Build script for Windows
REM Usage: build_windows.bat

echo ============================================
echo Bookmark Organizer Pro - Windows Build
echo ============================================

REM Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    exit /b 1
)

REM Check for PyInstaller
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

REM Check for optional dependencies
echo.
echo Checking dependencies...
pip install beautifulsoup4 requests Pillow pystray --quiet

REM Build
echo.
echo Building executable...
pyinstaller bookmark_organizer.spec --clean

if errorlevel 1 (
    echo.
    echo BUILD FAILED
    exit /b 1
)

echo.
echo ============================================
echo BUILD SUCCESSFUL
echo ============================================
echo Executable: dist\BookmarkOrganizerPro.exe
echo.

pause
