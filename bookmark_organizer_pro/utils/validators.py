"""URL and path validation utilities."""

from pathlib import Path
from typing import Tuple
from urllib.parse import urlparse

from ..constants import IS_WINDOWS


def validate_url(url: str) -> Tuple[bool, str]:
    """Validate a URL and return (is_valid, error_message)."""
    if not url:
        return False, "URL cannot be empty"

    if not isinstance(url, str):
        return False, "URL must be a string"

    url = url.strip()

    if len(url) > 2048:
        return False, "URL exceeds maximum length (2048 characters)"

    if not url.startswith(('http://', 'https://', 'file://', 'ftp://')):
        return False, "URL must start with http://, https://, file://, or ftp://"

    try:
        parsed = urlparse(url)
        if not parsed.netloc and not parsed.path:
            return False, "URL is malformed"
        return True, ""
    except Exception as e:
        return False, f"URL parsing error: {str(e)}"


def validate_path(path_str: str, must_exist: bool = False) -> Tuple[bool, str]:
    """Validate a file path and return (is_valid, error_message)."""
    if not path_str:
        return False, "Path cannot be empty"

    try:
        path = Path(path_str)

        if IS_WINDOWS:
            invalid_chars = '<>:"|?*'
            if any(c in str(path) for c in invalid_chars):
                return False, f"Path contains invalid characters: {invalid_chars}"

        if must_exist and not path.exists():
            return False, f"Path does not exist: {path}"

        return True, ""
    except Exception as e:
        return False, f"Path error: {str(e)}"
