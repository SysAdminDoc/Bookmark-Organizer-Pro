"""Performance benchmarks for core bookmark operations.

Run with: py -3.12 benchmarks/bench_core.py

Measures JSON load/save, keyword search, and bookmark add latency at
various library sizes. Results printed as a table to stdout.
"""

import importlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path


def _setup_env():
    tmp = tempfile.mkdtemp(prefix="bop_bench_")
    os.environ["BOOKMARK_DATA_DIR"] = tmp
    import bookmark_organizer_pro.constants as _c
    importlib.reload(_c)
    _c.ensure_directories()
    return tmp


def _make_bookmarks(n):
    from bookmark_organizer_pro.models import Bookmark
    return [
        Bookmark(
            id=i,
            url=f"https://example-{i}.com/page/{i % 100}",
            title=f"Benchmark Bookmark {i} — {'python' if i % 3 == 0 else 'javascript'} tutorial",
            category="Testing",
            tags=["bench", f"tag-{i % 20}"],
        )
        for i in range(n)
    ]


def bench_json_save_load(sizes=(100, 500, 1000, 5000)):
    from bookmark_organizer_pro.constants import MASTER_BOOKMARKS_FILE
    results = []
    for n in sizes:
        bookmarks = _make_bookmarks(n)
        data = [bm.to_dict() for bm in bookmarks]

        t0 = time.perf_counter()
        MASTER_BOOKMARKS_FILE.write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
        save_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        loaded = json.loads(MASTER_BOOKMARKS_FILE.read_text(encoding="utf-8"))
        load_ms = (time.perf_counter() - t0) * 1000

        size_kb = MASTER_BOOKMARKS_FILE.stat().st_size / 1024
        results.append((n, save_ms, load_ms, size_kb))
    return results


def bench_keyword_search(sizes=(100, 500, 1000, 5000)):
    from bookmark_organizer_pro.search import SearchEngine
    engine = SearchEngine()
    results = []
    for n in sizes:
        bookmarks = _make_bookmarks(n)

        t0 = time.perf_counter()
        hits = engine.search(bookmarks, "python tutorial")
        search_ms = (time.perf_counter() - t0) * 1000

        results.append((n, search_ms, len(hits)))
    return results


def bench_add_bookmark(count=500):
    from bookmark_organizer_pro.core import CategoryManager
    from bookmark_organizer_pro.managers import BookmarkManager, TagManager
    cm = CategoryManager()
    tm = TagManager()
    bm_mgr = BookmarkManager(cm, tm)

    t0 = time.perf_counter()
    for i in range(count):
        bm_mgr.add_bookmark_clean(
            url=f"https://bench-add-{i}.example.com",
            title=f"Bench Add {i}",
            category="Benchmark",
            tags=["bench"],
        )
    add_ms = (time.perf_counter() - t0) * 1000
    per_ms = add_ms / max(count, 1)
    return count, add_ms, per_ms


def main():
    tmp = _setup_env()
    try:
        print("=" * 70)
        print("Bookmark Organizer Pro — Performance Benchmarks")
        print("=" * 70)

        print("\n--- JSON Save/Load ---")
        print(f"{'Size':>8} {'Save(ms)':>10} {'Load(ms)':>10} {'File(KB)':>10}")
        for n, save, load, size in bench_json_save_load():
            print(f"{n:>8} {save:>10.1f} {load:>10.1f} {size:>10.1f}")

        print("\n--- Keyword Search ---")
        print(f"{'Size':>8} {'Search(ms)':>12} {'Hits':>6}")
        for n, ms, hits in bench_keyword_search():
            print(f"{n:>8} {ms:>12.2f} {hits:>6}")

        print("\n--- Add Bookmark (500x, includes categorization) ---")
        count, total, per = bench_add_bookmark()
        print(f"  {count} bookmarks in {total:.0f}ms ({per:.2f}ms/bookmark)")

        print("\n" + "=" * 70)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("BOOKMARK_DATA_DIR", None)


if __name__ == "__main__":
    main()
