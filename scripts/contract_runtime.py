"""Shared observability and cleanup helpers for repository contract scripts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence


class ContractTimeoutError(TimeoutError):
    """Raised when a contract phase or its whole run exceeds its budget."""


@dataclass
class PhaseRecord:
    name: str
    status: str
    elapsed_seconds: float = 0.0
    detail: str = ""


class ScriptWatchdog:
    """Report named phases and enforce elapsed budgets between checkpoints.

    Contract scripts are mostly GUI/browser code, so a watchdog cannot safely
    interrupt arbitrary Tk or Playwright calls from a helper thread. Instead,
    every blocking child process gets an explicit subprocess timeout and the
    script calls ``check`` at every phase boundary and polling loop. This keeps
    the timeout deterministic while allowing each script's resource cleanup to
    run normally.
    """

    def __init__(
        self,
        name: str,
        *,
        total_timeout: float,
        phase_timeout: float,
        artifact_dir: Path | None = None,
        stream=None,
    ) -> None:
        if total_timeout <= 0 or phase_timeout <= 0:
            raise ValueError("watchdog timeouts must be positive")
        self.name = name
        self.total_timeout = float(total_timeout)
        self.phase_timeout = float(phase_timeout)
        self.artifact_dir = artifact_dir.resolve() if artifact_dir else None
        self.stream = stream if stream is not None else sys.stderr
        self.started = time.monotonic()
        self._phase_started = self.started
        self._phase_name = "bootstrap"
        self.records: list[PhaseRecord] = []
        self._failed = False
        self._emit(f"phase {self._phase_name} started")
        self.write_report()

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.total_timeout - self.elapsed_seconds)

    def _emit(self, message: str) -> None:
        print(f"[{self.name}] {message}", file=self.stream, flush=True)

    def _close_phase(self, status: str = "passed", detail: str = "") -> None:
        elapsed = time.monotonic() - self._phase_started
        self.records.append(PhaseRecord(self._phase_name, status, elapsed, detail))
        self._emit(f"phase {self._phase_name} {status} ({elapsed:.1f}s){': ' + detail if detail else ''}")

    def check(self, detail: str = "") -> None:
        """Raise when the current phase or whole run has exhausted its budget."""
        elapsed = time.monotonic() - self._phase_started
        if elapsed >= self.phase_timeout:
            raise ContractTimeoutError(
                f"{self.name} phase {self._phase_name!r} exceeded "
                f"{self.phase_timeout:g}s{': ' + detail if detail else ''}"
            )
        total = self.elapsed_seconds
        if total >= self.total_timeout:
            raise ContractTimeoutError(
                f"{self.name} exceeded total watchdog of {self.total_timeout:g}s"
            )

    def phase(self, name: str) -> None:
        """Finish the prior phase and start a named phase."""
        self.check()
        self._close_phase()
        self._phase_name = name
        self._phase_started = time.monotonic()
        self._emit(f"phase {name} started")
        self.write_report()

    def finish(self) -> None:
        self.check()
        self._close_phase()
        self._phase_name = "complete"
        self._phase_started = time.monotonic()
        self._emit(f"completed in {self.elapsed_seconds:.1f}s")
        self.write_report()

    def fail(self, error: BaseException) -> None:
        """Record a failure without masking the original exception."""
        if self._failed:
            return
        self._failed = True
        elapsed = time.monotonic() - self._phase_started
        self.records.append(PhaseRecord(self._phase_name, "failed", elapsed, str(error)))
        self._emit(f"phase {self._phase_name} failed ({elapsed:.1f}s): {error}")
        self.write_report(error)

    def write_report(self, error: BaseException | None = None, *, extra: dict[str, Any] | None = None) -> Path | None:
        if self.artifact_dir is None:
            return None
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "script": self.name,
            "status": "failed" if error is not None else "passed",
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "total_timeout_seconds": self.total_timeout,
            "phase_timeout_seconds": self.phase_timeout,
            "phases": [asdict(record) for record in self.records],
        }
        if error is not None:
            payload["error"] = str(error)
            payload["traceback"] = "".join(traceback.format_exception(error))
        if extra:
            payload.update(extra)
        report_path = self.artifact_dir / "contract-report.json"
        report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report_path


def preserve_path(source: Path, destination: Path) -> Path | None:
    """Copy a failure artifact while tolerating an artifact that disappeared."""
    source = source.resolve()
    destination = destination.resolve()
    if not source.exists() or source == destination:
        return None
    if source.is_dir():
        try:
            destination.relative_to(source)
        except ValueError:
            pass
        else:
            return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)
    return destination


def terminate_process_tree(process: subprocess.Popen, *, grace_seconds: float = 5.0) -> None:
    """Terminate a child and all descendants, then wait for the root process."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            pass


def terminate_processes_with_marker(marker: str) -> None:
    """Kill Windows child trees whose command line contains a private marker."""
    if not marker or os.name != "nt":
        return
    query = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", query],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        raw = json.loads(completed.stdout or "[]")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return
    processes = raw if isinstance(raw, list) else [raw]
    pids = {
        int(item["ProcessId"])
        for item in processes
        if isinstance(item, dict)
        and marker in str(item.get("CommandLine") or "")
        and str(item.get("ProcessId") or "").isdigit()
    }
    for pid in sorted(pids):
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def bounded_subprocess(
    command: Sequence[str | Path],
    *,
    timeout: float,
    cwd: Path,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    """Run a child with an explicit timeout and clean up if it overruns."""
    process = subprocess.Popen([str(part) for part in command], cwd=cwd, **kwargs)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        terminate_process_tree(process)
        raise ContractTimeoutError(
            f"subprocess exceeded {timeout:g}s: {' '.join(str(part) for part in command)}"
        ) from exc
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
