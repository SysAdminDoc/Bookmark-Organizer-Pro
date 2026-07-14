@echo off
REM Build script for Windows
REM Usage: scripts\build_windows.bat

cd /d "%~dp0.."

echo ============================================
echo Bookmark Organizer Pro - Windows Build
echo ============================================

REM Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    exit /b 1
)

REM Build in an isolated Python 3.11 environment from the verified lock.
echo.
echo Building executable...
python scripts\build_release.py

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
