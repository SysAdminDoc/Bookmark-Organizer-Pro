"""Clean-shell entry-point and contract-runtime checks."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts.contract_runtime import ContractTimeoutError, ScriptWatchdog, terminate_process_tree
from benchmarks.bench_core import CASE_ORDER, run_benchmark


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_START = "<!-- clean-shell-contract:start -->"
CONTRACT_END = "<!-- clean-shell-contract:end -->"


def _documented_contract_commands() -> list[list[str]]:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    block = readme.split(CONTRACT_START, 1)[1].split(CONTRACT_END, 1)[0]
    return [
        shlex.split(line.strip())
        for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_documented_contract_commands_run_without_pythonpath() -> None:
    commands = _documented_contract_commands()
    assert commands
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        assert completed.returncode == 0, (
            f"documented command failed: {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )


def test_watchdog_records_named_phases_and_failure_artifact(tmp_path: Path) -> None:
    watchdog = ScriptWatchdog(
        "test-contract",
        total_timeout=1.0,
        phase_timeout=0.02,
        artifact_dir=tmp_path,
    )
    watchdog.phase("fixture")
    time.sleep(0.03)
    with pytest.raises(ContractTimeoutError):
        watchdog.check("fixture stalled")

    error = ContractTimeoutError("fixture stalled")
    watchdog.fail(error)
    report = json.loads((tmp_path / "contract-report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["phases"][-1]["name"] == "fixture"
    assert report["phases"][-1]["status"] == "failed"
    assert "fixture stalled" in report["traceback"]


def test_terminate_process_tree_reaps_child() -> None:
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    terminate_process_tree(process, grace_seconds=1)
    assert process.poll() is not None


def test_benchmark_report_has_bounded_named_workloads() -> None:
    report = run_benchmark(
        sizes=(8,),
        case_timeout_seconds=5.0,
        total_timeout_seconds=30.0,
    )

    assert report["schema_version"] == 1
    assert report["passed"] is True
    assert report["case_order"] == list(CASE_ORDER)
    assert [case["name"] for case in report["cases"]] == list(CASE_ORDER)
    assert all(case["status"] == "completed" for case in report["cases"])
    assert all(case["watchdog_ms"] == 5000.0 for case in report["cases"])
    dedupe = next(case for case in report["cases"] if case["name"] == "dedupe")
    assert dedupe["duplicates"] >= 1


def test_growth_budget_tightens_a_larger_tier_below_the_flat_ceiling() -> None:
    """R-178: the flat ceiling alone cannot see a complexity regression."""
    from benchmarks.bench_core import CASE_THRESHOLDS_MS, _case_threshold

    flat = _case_threshold("search", 2000, 2000)
    derived = _case_threshold("search", 2000, 2000, baseline=(200, 2.0))

    assert flat == CASE_THRESHOLDS_MS["search"]
    assert derived < flat
    # 2.0ms at 200 records, linear to 2000, times the noise tolerance.
    assert derived == pytest.approx(60.0, rel=0.01)


def test_growth_budget_scales_with_the_declared_class() -> None:
    from benchmarks.bench_core import _case_threshold

    linear = _case_threshold("search", 4000, 100_000, baseline=(1000, 10.0))
    log_linear = _case_threshold("sort", 4000, 100_000, baseline=(1000, 10.0))

    # n log n grows faster than n over the same span, so it earns more room.
    assert log_linear > linear


def test_a_case_that_cannot_grow_keeps_its_baseline_budget() -> None:
    from benchmarks.bench_core import GROWTH_FLOOR_MS, _case_threshold, CASE_GROWTH

    assert "constant" not in {CASE_GROWTH[case] for case in ("load", "search", "save")}
    # A floor keeps a sub-millisecond baseline from failing on noise alone.
    assert _case_threshold("sort", 10_000, 100_000, baseline=(100, 0.05)) == GROWTH_FLOOR_MS


def test_every_benchmark_case_declares_a_growth_class() -> None:
    from benchmarks.bench_core import CASE_GROWTH, CASE_ORDER, CASE_THRESHOLDS_MS

    assert set(CASE_GROWTH) == set(CASE_ORDER) == set(CASE_THRESHOLDS_MS)
    assert set(CASE_GROWTH.values()) <= {"constant", "linear", "n_log_n"}
