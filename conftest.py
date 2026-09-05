"""Process-wide test isolation, established before any application import.

pytest imports the root conftest before it collects a single test module, which
is the only point early enough to matter here. ``constants`` reads
``BOOKMARK_DATA_DIR`` once at import and every module that needs a path binds
the resulting value at ITS import, so a per-class ``setUpClass`` that sets the
variable and reloads ``constants`` cannot redirect anything already imported.
That is not theoretical: on 2026-09-05 the user's real library at
``~/.bookmark_organizer/master_bookmarks.json`` held 141 records, 141 of them
created by this suite, because the CLI and integration cases wrote there
whenever another test module had been imported first.

Setting the variable here, before the first application import, redirects every
consumer including the ones that capture a path at import time, and subprocesses
inherit it through the environment.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

import pytest


# Paths the application uses when BOOKMARK_DATA_DIR is unset. Recorded before
# the variable is set so the canary can check them without importing anything.
_REAL_DATA_DIR = Path(os.path.expanduser("~")) / ".bookmark_organizer"
_PROTECTED_PATHS = tuple(
    _REAL_DATA_DIR / name
    for name in (
        "master_bookmarks.json",
        "categories.json",
        "tags.json",
        "ai_config.json",
        "settings.json",
        "api_token.txt",
        "mcp_tokens.json",
        "extension_origins.json",
    )
)


def _install_isolated_data_dir() -> str:
    """Point the application at a throwaway directory for this session."""
    existing = os.environ.get("BOOKMARK_DATA_DIR")
    if existing:
        # An outer harness already isolated us; do not fight it.
        return existing
    session_dir = tempfile.mkdtemp(prefix="bop_test_data_")
    os.environ["BOOKMARK_DATA_DIR"] = session_dir
    atexit.register(shutil.rmtree, session_dir, ignore_errors=True)
    return session_dir


SESSION_DATA_DIR = _install_isolated_data_dir()


def _protected_state() -> dict:
    """Fingerprint every protected real path without creating any of them."""
    state = {}
    for path in _PROTECTED_PATHS:
        try:
            state[str(path)] = path.read_bytes() if path.is_file() else None
        except OSError:
            state[str(path)] = None
    return state


@pytest.fixture(scope="session", autouse=True)
def _real_library_is_never_touched():
    """Fail the run if anything wrote to the user's own data directory."""
    before = _protected_state()
    yield
    after = _protected_state()
    changed = sorted(
        path for path, content in after.items() if before.get(path) != content
    )
    assert not changed, (
        "the test suite wrote to the user's real data directory: "
        + ", ".join(changed)
        + "\nA module that captures a path at import time cannot be redirected "
        "by a later setUpClass; isolate through BOOKMARK_DATA_DIR in conftest."
    )
