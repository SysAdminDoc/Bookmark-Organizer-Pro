#!/usr/bin/env python3
"""Lint and temporarily install the Firefox extension in a clean profile."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_extension import DEFAULT_OUTPUT, build_target
from scripts.contract_runtime import ScriptWatchdog, preserve_path, terminate_process_tree


WEB_EXT_VERSION = "8.9.0"
INSTALL_MARKER = "as a temporary add-on"
PROFILE_MARKER = "Creating new Firefox profile"


def discover_firefox(explicit: str = "") -> Path | None:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    configured = os.getenv("FIREFOX_BINARY", "").strip()
    if configured:
        candidates.append(Path(configured))
    if os.name == "nt":
        candidates.extend([
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Mozilla Firefox/firefox.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Mozilla Firefox/firefox.exe",
        ])
        playwright = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
        candidates.extend(
            sorted(playwright.glob("firefox-*/firefox/firefox.exe"), reverse=True)
        )
    else:
        found = shutil.which("firefox")
        if found:
            candidates.append(Path(found))
    return next((path.resolve() for path in candidates if path.is_file()), None)


def _npx_command() -> str:
    command = shutil.which("npx.cmd" if os.name == "nt" else "npx")
    if not command:
        raise RuntimeError("Firefox smoke requires Node.js npx and web-ext")
    return command


def lint_command(source_dir: Path) -> list[str]:
    return [
        _npx_command(), "--yes", f"web-ext@{WEB_EXT_VERSION}", "lint",
        "--source-dir", str(source_dir), "--output", "json", "--no-config-discovery",
    ]


def runtime_command(source_dir: Path, firefox: Path) -> list[str]:
    return [
        _npx_command(), "--yes", f"web-ext@{WEB_EXT_VERSION}", "run",
        "--source-dir", str(source_dir), "--firefox", str(firefox),
        "--no-reload", "--no-input", "--no-config-discovery", "--args=-headless", "--verbose",
    ]


def _stop_process_tree(process: subprocess.Popen) -> None:
    terminate_process_tree(process)


def run_smoke(
    source_dir: Path,
    firefox: Path,
    timeout: float = 25.0,
    *,
    total_timeout: float = 120.0,
    phase_timeout: float = 60.0,
    artifact_dir: Path | None = None,
) -> dict[str, object]:
    watchdog = ScriptWatchdog(
        "firefox-smoke",
        total_timeout=total_timeout,
        phase_timeout=phase_timeout,
        artifact_dir=artifact_dir,
    )
    log_path: Path | None = None
    process: subprocess.Popen | None = None
    output = ""
    try:
        watchdog.phase("web-ext-lint")
        lint_timeout = min(60.0, watchdog.remaining_seconds)
        lint = subprocess.run(
            lint_command(source_dir), capture_output=True, text=True,
            timeout=max(1.0, lint_timeout), check=False,
        )
        if lint.returncode:
            raise RuntimeError(f"Firefox web-ext lint failed: {(lint.stdout + lint.stderr)[-1200:]}")
        lint_report = json.loads(lint.stdout)

        watchdog.phase("temporary-install")
        with tempfile.NamedTemporaryFile(prefix="bop-firefox-smoke-", suffix=".log", delete=False) as handle:
            log_path = Path(handle.name)
            process = subprocess.Popen(
                runtime_command(source_dir, firefox),
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=os.name != "nt",
            )
        deadline = time.monotonic() + max(5.0, timeout)
        while time.monotonic() < deadline:
            watchdog.check("waiting for Firefox temporary install")
            output = log_path.read_text(encoding="utf-8", errors="replace")
            if INSTALL_MARKER in output or process.poll() is not None:
                break
            time.sleep(0.25)

        if process is not None:
            _stop_process_tree(process)
        output = log_path.read_text(encoding="utf-8", errors="replace")
        if PROFILE_MARKER not in output:
            raise RuntimeError("web-ext did not create a clean Firefox profile")
        if INSTALL_MARKER not in output:
            tail = "\n".join(output.splitlines()[-12:])
            raise RuntimeError(f"Firefox did not install the temporary add-on within {timeout:g}s\n{tail}")
        watchdog.finish()
        return {
            "browser": "firefox",
            "binary": str(firefox),
            "clean_profile": True,
            "temporary_addon_installed": True,
            "lint": lint_report.get("summary", {}),
        }
    except BaseException as exc:
        if log_path is not None and log_path.exists() and artifact_dir is not None:
            preserve_path(log_path, artifact_dir / "web-ext.log")
        watchdog.fail(exc)
        raise
    finally:
        if process is not None:
            _stop_process_tree(process)
        if log_path is not None:
            for _attempt in range(10):
                try:
                    log_path.unlink(missing_ok=True)
                    break
                except PermissionError:
                    time.sleep(0.1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firefox", default="", help="Firefox executable; also accepts FIREFOX_BINARY")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--total-timeout", type=float, default=120.0)
    parser.add_argument("--phase-timeout", type=float, default=60.0)
    parser.add_argument(
        "--artifact-dir", type=Path,
        default=ROOT / "build" / "diagnostics" / "firefox-smoke",
        help="preserve phase report and runtime log here when the smoke fails",
    )
    args = parser.parse_args(argv)
    artifact = build_target("firefox", args.output)
    firefox = discover_firefox(args.firefox)
    if firefox is None:
        print(json.dumps({
            "status": "unavailable",
            "limitation": "Firefox runtime was not found; the deterministic build and web-ext lint remain available.",
            "artifact": artifact,
        }, indent=2))
        return 2
    report = run_smoke(
        Path(str(artifact["directory"])), firefox, args.timeout,
        total_timeout=args.total_timeout,
        phase_timeout=args.phase_timeout,
        artifact_dir=args.artifact_dir,
    )
    print(json.dumps({"status": "passed", "artifact": artifact, "runtime": report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
