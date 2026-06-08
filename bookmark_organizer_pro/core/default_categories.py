"""Default categorization patterns across 43 categories.

Cross-referenced from IAB Content Taxonomy, DMOZ/Open Directory, FortiGuard Web
Filter, and Google News categories. 40 top-level content categories plus 3
infrastructure categories (URL Shorteners, Internal Networks, Link Aggregators).
Pattern types: domain:, keyword:, regex:, path:, title:.

The pattern data itself lives in the sibling ``default_categories.json`` asset
rather than inline here — it is ~7,500 mostly-static entries, so keeping it as
data keeps this module tiny and lets the patterns be edited without touching
source. ``DEFAULT_CATEGORIES`` is loaded from that file at import time, with an
empty-dict fallback (plus a logged warning) if the asset is ever missing or
corrupt, so callers always get a usable mapping.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from ..logging_config import log

_DATA_FILE = Path(__file__).with_name("default_categories.json")


def _load_default_categories() -> Dict[str, List[str]]:
    """Load the bundled default category → patterns mapping from JSON."""
    try:
        with open(_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            log.error(f"{_DATA_FILE.name} is not a JSON object; using empty defaults")
            return {}
        # Normalize to {str: [str, ...]} defensively.
        return {
            str(name): [str(p) for p in patterns]
            for name, patterns in data.items()
            if isinstance(patterns, (list, tuple))
        }
    except FileNotFoundError:
        log.error(f"Default categories asset missing: {_DATA_FILE}; using empty defaults")
        return {}
    except Exception as e:  # pragma: no cover - corrupt asset is a deploy error
        log.error(f"Could not load default categories from {_DATA_FILE}: {e}")
        return {}


DEFAULT_CATEGORIES: Dict[str, List[str]] = _load_default_categories()
