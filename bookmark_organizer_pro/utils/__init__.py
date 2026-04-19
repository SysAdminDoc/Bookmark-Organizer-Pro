"""Utility functions for Bookmark Organizer Pro."""

from .safe import (
    safe_int, safe_float, safe_str, safe_get, safe_list_get,
    safe_divide, safe_json_loads, safe_json_dumps, safe_get_domain,
    safe_invoke_callback, safe_slice, clamp, truncate_string,
    sanitize_filename, validate_config,
)
from .validators import validate_url, validate_path
from .url import normalize_url, TRACKING_PARAMS
from .metadata import fetch_page_metadata, wayback_check, wayback_save
from .health import calculate_health_score, merge_duplicate_bookmarks
from .dependencies import DependencyManager
from .runtime import (
    ResourceManager,
    atomic_json_write,
    csv_safe_cell,
    get_user_friendly_error,
    open_external_url,
    run_with_timeout,
    validate_environment,
)

__all__ = [
    # safe.py
    "safe_int", "safe_float", "safe_str", "safe_get", "safe_list_get",
    "safe_divide", "safe_json_loads", "safe_json_dumps", "safe_get_domain",
    "safe_invoke_callback", "safe_slice", "clamp", "truncate_string",
    "sanitize_filename", "validate_config",
    # validators.py
    "validate_url", "validate_path",
    # url.py
    "normalize_url", "TRACKING_PARAMS",
    # metadata.py
    "fetch_page_metadata", "wayback_check", "wayback_save",
    # health.py
    "calculate_health_score", "merge_duplicate_bookmarks",
    # dependencies.py
    "DependencyManager",
    # runtime.py
    "ResourceManager", "atomic_json_write", "csv_safe_cell",
    "get_user_friendly_error", "open_external_url", "run_with_timeout",
    "validate_environment",
]
