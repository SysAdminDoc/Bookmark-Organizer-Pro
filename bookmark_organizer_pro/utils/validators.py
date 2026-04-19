"""URL and path validation utilities."""

import re
import ipaddress
from pathlib import Path, PureWindowsPath
from typing import Tuple
from urllib.parse import urlparse

from ..constants import IS_WINDOWS


def validate_url(url: str) -> Tuple[bool, str]:
    """Validate a URL and return (is_valid, error_message)."""
    if not isinstance(url, str):
        return False, "URL must be a string"

    url = url.strip()
    if not url:
        return False, "URL cannot be empty"

    if len(url) > 2048:
        return False, "URL exceeds maximum length (2048 characters)"

    if any(ch.isspace() or ord(ch) < 32 for ch in url):
        return False, "URL cannot contain whitespace or control characters"

    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https", "file", "ftp"}:
            return False, "URL must start with http://, https://, file://, or ftp://"

        if scheme in {"http", "https", "ftp"}:
            hostname = parsed.hostname
            if not hostname:
                return False, "URL must include a host name"
            try:
                parsed.port
            except ValueError:
                return False, "URL port is malformed"
            if len(hostname) > 253:
                return False, "Host name is too long"
            if not _is_valid_hostname(hostname):
                return False, "Host name is malformed"

        if scheme == "file" and not (parsed.netloc or parsed.path):
            return False, "URL is malformed"
        return True, ""
    except Exception as e:
        return False, f"URL parsing error: {str(e)}"


def _is_valid_hostname(hostname: str) -> bool:
    """Validate DNS names while allowing IPv4/IPv6 literals."""
    host = str(hostname or "").strip()
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass

    try:
        ascii_host = host.encode("idna").decode("ascii").rstrip(".")
    except UnicodeError:
        return False
    if not ascii_host or len(ascii_host) > 253:
        return False

    labels = ascii_host.split(".")
    label_pattern = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
    return all(label_pattern.match(label or "") for label in labels)


def validate_path(path_str: str, must_exist: bool = False) -> Tuple[bool, str]:
    """Validate a file path and return (is_valid, error_message)."""
    if not isinstance(path_str, str):
        return False, "Path must be a string"

    path_str = path_str.strip()
    if not path_str:
        return False, "Path cannot be empty"

    try:
        if "\x00" in path_str or any(ord(ch) < 32 for ch in path_str):
            return False, "Path cannot contain control characters"

        if IS_WINDOWS:
            win_path = PureWindowsPath(path_str)
            invalid_chars = '<>:"|?*'
            reserved_names = {
                "CON", "PRN", "AUX", "NUL",
                *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10)),
            }
            for part in win_path.parts:
                if part in (win_path.anchor, win_path.drive, "\\", "/"):
                    continue
                if any(c in part for c in invalid_chars):
                    return False, f"Path contains invalid characters: {invalid_chars}"
                stem = part.split(".", 1)[0].upper()
                if stem in reserved_names:
                    return False, f"Path uses reserved Windows name: {stem}"
                if re.search(r"[ .]$", part):
                    return False, "Windows path segments cannot end with a space or period"

        path = Path(path_str)

        if must_exist and not path.exists():
            return False, f"Path does not exist: {path}"

        return True, ""
    except Exception as e:
        return False, f"Path error: {str(e)}"
