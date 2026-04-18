"""Safe wrappers for common operations with default fallbacks."""

import json
import re
from urllib.parse import urlparse

from ..logging_config import log


def safe_int(value, default: int = 0) -> int:
    """Safely convert value to int with default fallback."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value, default: float = 0.0) -> float:
    """Safely convert value to float with default fallback."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_str(value, default: str = "") -> str:
    """Safely convert value to string with default fallback."""
    if value is None:
        return default
    try:
        return str(value)
    except Exception:
        return default


def safe_get(dictionary: dict, key: str, default=None):
    """Safely get value from dictionary with type checking."""
    if dictionary is None or not isinstance(dictionary, dict):
        return default
    return dictionary.get(key, default)


def safe_list_get(lst: list, index: int, default=None):
    """Safely get item from list by index."""
    if lst is None or not isinstance(lst, (list, tuple)):
        return default
    try:
        return lst[index]
    except (IndexError, TypeError):
        return default


def safe_divide(numerator, denominator, default: float = 0.0) -> float:
    """Safely divide with zero-division protection."""
    try:
        if denominator == 0:
            return default
        return float(numerator) / float(denominator)
    except (ValueError, TypeError, ZeroDivisionError):
        return default


def truncate_string(s: str, max_length: int, suffix: str = "...") -> str:
    """Safely truncate a string to maximum length."""
    if not s or not isinstance(s, str):
        return ""
    if len(s) <= max_length:
        return s
    return s[:max_length - len(suffix)] + suffix


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename by removing invalid characters."""
    if not filename:
        return "unnamed"

    invalid_chars = '<>:"/\\|?*\x00-\x1f'
    sanitized = re.sub(f'[{invalid_chars}]', '_', filename)
    sanitized = sanitized.strip(' .')

    if not sanitized:
        return "unnamed"

    return sanitized[:255]


def safe_json_loads(json_str: str, default=None):
    """Safely parse JSON string with error handling."""
    if not json_str:
        return default
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        log.warning(f"JSON parse error: {e}")
        return default


def safe_json_dumps(obj, default: str = "{}") -> str:
    """Safely serialize object to JSON string."""
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as e:
        log.warning(f"JSON serialize error: {e}")
        return default


def safe_get_domain(url: str) -> str:
    """Safely extract domain from URL."""
    if not url or not isinstance(url, str):
        return ""
    try:
        parsed = urlparse(url)
        return (parsed.netloc or "").replace("www.", "")
    except Exception:
        return ""


def validate_config(config: dict, required_keys: list = None, defaults: dict = None) -> dict:
    """Validate and fill missing config values."""
    if config is None:
        config = {}

    if not isinstance(config, dict):
        log.warning("Config is not a dictionary, using defaults")
        config = {}

    if defaults:
        for key, value in defaults.items():
            if key not in config:
                config[key] = value

    if required_keys:
        for key in required_keys:
            if key not in config:
                log.warning(f"Missing required config key: {key}")

    return config


def safe_invoke_callback(callback, *args, **kwargs):
    """Safely invoke a callback with error handling."""
    if callback is None:
        return None
    try:
        return callback(*args, **kwargs)
    except Exception as e:
        log.warning(f"Callback invocation failed: {e}")
        return None


def clamp(value, min_val, max_val):
    """Clamp a value to a range."""
    try:
        return max(min_val, min(max_val, value))
    except (TypeError, ValueError):
        return min_val


def safe_slice(lst, start: int = 0, end: int = None, default=None):
    """Safely slice a list with bounds checking."""
    if lst is None or not isinstance(lst, (list, tuple)):
        return default if default is not None else []
    try:
        return lst[start:end] if end is not None else lst[start:]
    except Exception:
        return default if default is not None else []
