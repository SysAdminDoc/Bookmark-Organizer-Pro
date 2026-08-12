"""Bounded performance benchmarks for realistic bookmark workloads.

Run the human-readable gate with::

    py -3.12 benchmarks/bench_core.py --gate

The default collection sizes are 100, 1,000, and 5,000 bookmarks. Fixture
creation is bulk work outside measured regions. Each named case runs in an
isolated worker with a hard watchdog so a slow persistence path cannot stall
the complete gate. Add ``--json`` or ``--output report.json`` for the stable
machine-readable report.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_SIZES = (100, 1_000, 5_000)
DEFAULT_CASE_TIMEOUT_SECONDS = 10.0
DEFAULT_TOTAL_TIMEOUT_SECONDS = 60.0
CASE_ORDER = (
    "startup_cold",
    "startup_warm",
    "load",
    "search",
    "sort",
    "save",
    "dedupe",
    "incremental_add",
)

# These are intentionally local-machine budgets, not universal SLAs. The
# largest default collection is the gate point; smaller collections use the
# same ceiling so fixed interpreter/storage overhead is not overfit.
CASE_THRESHOLDS_MS = {
    "startup_cold": 2_500.0,
    "startup_warm": 1_000.0,
    "load": 1_000.0,
    "search": 750.0,
    "sort": 750.0,
    "save": 3_000.0,
    "dedupe": 3_000.0,
    "incremental_add": 5_000.0,
}


def _make_bookmarks(count: int) -> list[Any]:
    """Build deterministic, varied records without touching the library."""

    from bookmark_organizer_pro.models import Bookmark

    created_at = "2026-01-01T00:00:00+00:00"
    bookmarks = []
    for index in range(count):
        base_url = f"https://example-{index % 250}.test/articles/{index}"
        if index == 1 or (index and index % 97 == 0):
            # One normalized duplicate per 97 records exercises the real URL
            # canonicalization path without making the fixture synthetic-only.
            duplicate_index = index - 1
            url = f"https://example-{duplicate_index % 250}.test/articles/{duplicate_index}?utm_source=benchmark"
        else:
            url = base_url
        language = "python" if index % 3 == 0 else "javascript"
        bookmarks.append(
            Bookmark(
                id=index + 1,
                url=url,
                title=f"{language.title()} research tutorial {index:05d}",
                category="Testing" if index % 2 else "Research",
                tags=["benchmark", f"topic-{index % 20}"],
                description="Deterministic benchmark fixture for local search and archival workflows.",
                created_at=created_at,
                modified_at=created_at,
            )
        )
    return bookmarks


def _fixture_payload(bookmarks: list[Any]) -> dict[str, Any]:
    from bookmark_organizer_pro.core.storage_manager import StorageManager

    return {
        "version": StorageManager.CURRENT_VERSION,
        "revision": 1,
        "metadata": {"saved_at": "2026-01-01T00:00:00+00:00", "count": len(bookmarks)},
        "data": [bookmark.to_dict() for bookmark in bookmarks],
    }


def _write_fixture(path: Path, bookmarks: list[Any]) -> None:
    """Write a current-schema fixture as setup, never as a timed case."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_fixture_payload(bookmarks), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _write_support_files(directory: Path) -> tuple[Path, Path]:
    """Use tiny explicit category/tag files so setup cost stays predictable."""

    categories = directory / "categories.json"
    categories.write_text(
        json.dumps(
            {
                "Research": [],
                "Testing": [],
                "Uncategorized / Needs Review": [],
            }
        ),
        encoding="utf-8",
    )
    tags = directory / "tags.json"
    tags.write_text(json.dumps({"version": 1, "tags": []}), encoding="utf-8")
    return categories, tags


def _manager(library: Path, categories: Path, tags: Path):
    from bookmark_organizer_pro.core import CategoryManager
    from bookmark_organizer_pro.managers import BookmarkManager, TagManager

    category_manager = CategoryManager(filepath=categories)
    tag_manager = TagManager(filepath=tags)
    return BookmarkManager(
        category_manager,
        tag_manager,
        filepath=library,
        storage_backend="json",
    )


def _worker_case(case: str, library: Path, save_target: Path, categories: Path, tags: Path) -> dict[str, Any]:
    """Run one timed case in a fresh process with imports outside warm timing."""

    if case == "startup_cold":
        started = time.perf_counter()
        manager = _manager(library, categories, tags)
        duration_ms = (time.perf_counter() - started) * 1000
        return {"duration_ms": duration_ms, "count": len(manager.get_all_bookmarks())}

    # Import and fixture loading are setup for all non-cold cases. The
    # operation timer starts only after the data needed by that operation is in
    # memory, making the rows comparable rather than measuring setup repeatedly.
    from bookmark_organizer_pro.core.storage_manager import StorageManager
    from bookmark_organizer_pro.search import SearchEngine

    if case == "startup_warm":
        _manager(library, categories, tags)
        started = time.perf_counter()
        manager = _manager(library, categories, tags)
        duration_ms = (time.perf_counter() - started) * 1000
        return {"duration_ms": duration_ms, "count": len(manager.get_all_bookmarks())}

    if case == "load":
        storage = StorageManager(library)
        started = time.perf_counter()
        bookmarks = storage.load()
        duration_ms = (time.perf_counter() - started) * 1000
        return {"duration_ms": duration_ms, "count": len(bookmarks)}

    storage = StorageManager(library)
    bookmarks = storage.load()

    if case == "search":
        engine = SearchEngine()
        started = time.perf_counter()
        hits = engine.search(bookmarks, "python research tutorial")
        duration_ms = (time.perf_counter() - started) * 1000
        return {"duration_ms": duration_ms, "hits": len(hits)}

    if case == "sort":
        started = time.perf_counter()
        ordered = sorted(
            bookmarks,
            key=lambda bookmark: (bookmark.title.casefold(), bookmark.created_at, bookmark.id),
        )
        duration_ms = (time.perf_counter() - started) * 1000
        return {"duration_ms": duration_ms, "count": len(ordered)}

    if case == "save":
        save_storage = StorageManager(save_target)
        save_storage.load()
        started = time.perf_counter()
        revision = save_storage.save(
            [bookmark.to_dict() for bookmark in bookmarks],
            expected_revision=save_storage.revision,
        )
        duration_ms = (time.perf_counter() - started) * 1000
        return {"duration_ms": duration_ms, "revision": revision}

    if case == "dedupe":
        manager = _manager(library, categories, tags)
        started = time.perf_counter()
        duplicate_groups = manager.find_duplicates()
        duration_ms = (time.perf_counter() - started) * 1000
        return {
            "duration_ms": duration_ms,
            "groups": len(duplicate_groups),
            "duplicates": sum(len(items) - 1 for items in duplicate_groups.values()),
        }

    if case == "incremental_add":
        manager = _manager(library, categories, tags)
        started = time.perf_counter()
        bookmark = manager.add_bookmark_clean(
            url="https://benchmark-incremental.example.test/new-entry",
            title="Incremental benchmark entry",
            category="Testing",
            tags=["benchmark", "incremental"],
        )
        duration_ms = (time.perf_counter() - started) * 1000
        return {"duration_ms": duration_ms, "saved": bookmark is not None}

    raise ValueError(f"unknown benchmark case: {case}")


def _worker_main(argv: list[str]) -> int:
    if len(argv) != 6:
        print("worker usage: --worker CASE LIBRARY SAVE_TARGET CATEGORIES TAGS", file=sys.stderr)
        return 2
    _, case, library, save_target, categories, tags = argv
    try:
        result = _worker_case(
            case,
            Path(library),
            Path(save_target),
            Path(categories),
            Path(tags),
        )
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}), file=sys.stdout)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


def _run_case(
    case: str,
    library: Path,
    save_target: Path,
    categories: Path,
    tags: Path,
    *,
    timeout_seconds: float,
    environment: dict[str, str],
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        case,
        str(library),
        str(save_target),
        str(categories),
        str(tags),
    ]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "name": case,
            "status": "timed_out",
            "duration_ms": None,
            "wall_ms": (time.perf_counter() - started) * 1000,
            "detail": f"exceeded {timeout_seconds:.1f}s worker watchdog",
        }

    wall_ms = (time.perf_counter() - started) * 1000
    output = completed.stdout.strip().splitlines()
    payload: dict[str, Any] = {}
    if output:
        try:
            payload = json.loads(output[-1])
        except json.JSONDecodeError:
            payload = {}
    if completed.returncode != 0 or "error" in payload:
        detail = payload.get("error") or completed.stderr.strip() or "worker failed"
        return {
            "name": case,
            "status": "failed",
            "duration_ms": None,
            "wall_ms": wall_ms,
            "detail": detail,
        }
    return {
        "name": case,
        "status": "completed",
        "duration_ms": round(float(payload.get("duration_ms", 0.0)), 3),
        "wall_ms": round(wall_ms, 3),
        **{key: value for key, value in payload.items() if key != "duration_ms"},
    }


def _parse_sizes(raw: str) -> tuple[int, ...]:
    values = []
    for item in str(raw).split(","):
        item = item.strip()
        if not item:
            continue
        try:
            value = int(item)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"invalid collection size: {item!r}") from exc
        if value <= 0:
            raise argparse.ArgumentTypeError("collection sizes must be positive")
        values.append(value)
    if not values:
        raise argparse.ArgumentTypeError("at least one collection size is required")
    return tuple(sorted(set(values)))


def _case_threshold(case: str, size: int, largest_size: int) -> float:
    # A fixed lower bound keeps interpreter startup from making tiny fixtures
    # look like failures while still making the report explicit per case.
    base = CASE_THRESHOLDS_MS[case]
    scale = max(1.0, size / max(largest_size, 1))
    return round(max(base * 0.5, base * scale), 3)


def run_benchmark(
    *,
    sizes: tuple[int, ...] = DEFAULT_SIZES,
    case_timeout_seconds: float = DEFAULT_CASE_TIMEOUT_SECONDS,
    total_timeout_seconds: float = DEFAULT_TOTAL_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run all bounded cases and return the versioned report structure."""

    if case_timeout_seconds <= 0 or total_timeout_seconds <= 0:
        raise ValueError("watchdog budgets must be positive")
    sizes = tuple(sorted(set(int(size) for size in sizes)))
    if not sizes or any(size <= 0 for size in sizes):
        raise ValueError("collection sizes must be positive")

    started = time.perf_counter()
    temporary_root = Path(tempfile.mkdtemp(prefix="bop_bench_"))
    data_dir = temporary_root / "runtime-data"
    environment = os.environ.copy()
    environment["BOOKMARK_DATA_DIR"] = str(data_dir)
    environment.pop("PYTHONPATH", None)
    cases: list[dict[str, Any]] = []
    violations: list[str] = []
    largest_size = max(sizes)
    try:
        for size in sizes:
            if time.perf_counter() - started >= total_timeout_seconds:
                for case in CASE_ORDER:
                    cases.append(
                        {
                            "name": case,
                            "size": size,
                            "status": "not_run",
                            "duration_ms": None,
                            "watchdog_ms": round(case_timeout_seconds * 1000, 3),
                            "threshold_ms": _case_threshold(case, size, largest_size),
                            "detail": "total benchmark watchdog exhausted before setup",
                        }
                    )
                break

            fixture_dir = temporary_root / f"collection-{size}"
            fixture_dir.mkdir(parents=True, exist_ok=True)
            bookmarks = _make_bookmarks(size)
            library = fixture_dir / "library.json"
            save_target = fixture_dir / "save-target.json"
            _write_fixture(library, bookmarks)
            _write_fixture(save_target, bookmarks)
            categories, tags = _write_support_files(fixture_dir)

            for case in CASE_ORDER:
                remaining = total_timeout_seconds - (time.perf_counter() - started)
                if remaining <= 0:
                    result = {
                        "name": case,
                        "status": "timed_out",
                        "duration_ms": None,
                        "wall_ms": 0.0,
                        "detail": "total benchmark watchdog exhausted",
                    }
                else:
                    result = _run_case(
                        case,
                        library,
                        save_target,
                        categories,
                        tags,
                        timeout_seconds=min(case_timeout_seconds, remaining),
                        environment=environment,
                    )
                threshold = _case_threshold(case, size, largest_size)
                result.update(
                    {
                        "size": size,
                        "watchdog_ms": round(case_timeout_seconds * 1000, 3),
                        "threshold_ms": threshold,
                    }
                )
                if result["status"] != "completed":
                    violations.append(f"{case}@{size}: {result.get('detail', result['status'])}")
                elif result["duration_ms"] > threshold:
                    result["status"] = "over_budget"
                    violations.append(
                        f"{case}@{size}: {result['duration_ms']:.1f}ms > {threshold:.1f}ms budget"
                    )
                cases.append(result)
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)

    return {
        "schema_version": 1,
        "sizes": list(sizes),
        "cases": cases,
        "case_order": list(CASE_ORDER),
        "thresholds_ms": CASE_THRESHOLDS_MS,
        "budgets": {
            "case_timeout_seconds": case_timeout_seconds,
            "total_timeout_seconds": total_timeout_seconds,
        },
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "violations": violations,
        "passed": not violations,
    }


def _print_human_report(report: dict[str, Any]) -> None:
    print("Bookmark Organizer Pro — bounded performance benchmark")
    print(
        f"sizes={','.join(str(size) for size in report['sizes'])} "
        f"elapsed={report['elapsed_ms']:.0f}ms "
        f"budget={report['budgets']['total_timeout_seconds']:.1f}s"
    )
    print(f"{'Size':>8} {'Case':<18} {'Time(ms)':>10} {'Budget':>10} {'Status':<12}")
    for case in report["cases"]:
        duration = "—" if case["duration_ms"] is None else f"{case['duration_ms']:.1f}"
        print(
            f"{case['size']:>8} {case['name']:<18} {duration:>10} "
            f"{case['threshold_ms']:>10.1f} {case['status']:<12}"
        )
    if report["violations"]:
        print("\nPERFORMANCE VIOLATIONS:")
        for violation in report["violations"]:
            print(f"  FAIL: {violation}")
    else:
        print("\nAll benchmark cases completed within their budgets.")


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] == "--worker":
        return _worker_main(raw_argv)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", action="store_true", help="return failure when a case exceeds its budget")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--output", type=Path, help="write the machine-readable report to this path")
    parser.add_argument(
        "--sizes",
        type=_parse_sizes,
        default=DEFAULT_SIZES,
        help="comma-separated collection sizes (default: 100,1000,5000)",
    )
    parser.add_argument(
        "--case-timeout",
        type=float,
        default=DEFAULT_CASE_TIMEOUT_SECONDS,
        help=f"hard worker watchdog in seconds (default: {DEFAULT_CASE_TIMEOUT_SECONDS:g})",
    )
    parser.add_argument(
        "--total-timeout",
        type=float,
        default=DEFAULT_TOTAL_TIMEOUT_SECONDS,
        help=f"total benchmark watchdog in seconds (default: {DEFAULT_TOTAL_TIMEOUT_SECONDS:g})",
    )
    args = parser.parse_args(raw_argv)
    if args.case_timeout <= 0 or args.total_timeout <= 0:
        parser.error("--case-timeout and --total-timeout must be positive")

    report = run_benchmark(
        sizes=args.sizes,
        case_timeout_seconds=args.case_timeout,
        total_timeout_seconds=args.total_timeout,
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    if args.json:
        print(encoded)
    else:
        _print_human_report(report)
        if args.output:
            print(f"\nJSON report: {args.output}")
    return 1 if args.gate and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
