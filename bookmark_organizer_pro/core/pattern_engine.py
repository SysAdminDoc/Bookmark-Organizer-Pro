"""Pattern engine for URL/title-based auto-categorization.

Supports multiple pattern types:
- domain:example.com     — exact or suffix domain match
- path:/some/path        — URL path substring match
- keyword:foo            — substring match in URL or title
- title:foo              — substring match in title only
- ext:pdf                — file extension match
- regex:pattern          — regex match against URL or title

Uses a two-pass priority system with O(1) domain lookup via dict indexing.
Pass 1 checks domain/path/extension (most specific), Pass 2 checks
keyword/title/regex (broader). This prevents generic keywords from
overriding exact domain matches.
"""

import re
import signal
import sys
from collections import defaultdict
from collections.abc import Iterable
from typing import Dict, List, Optional
from urllib.parse import urlparse

_IS_WINDOWS = sys.platform == "win32"
_REGEX_TIMEOUT_SECONDS = 2


def _safe_regex_search(pattern, text: str):
    """Run regex search with a timeout guard (Unix signal or catch-all on Windows)."""
    if _IS_WINDOWS:
        try:
            return pattern.search(text)
        except (RecursionError, MemoryError):
            return None
    else:
        def _alarm_handler(signum, frame):
            raise TimeoutError("Regex match timed out")
        old = signal.signal(signal.SIGALRM, _alarm_handler)
        signal.alarm(_REGEX_TIMEOUT_SECONDS)
        try:
            return pattern.search(text)
        except (TimeoutError, RecursionError, MemoryError):
            return None
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)


class PatternEngine:
    """URL/title pattern matching for auto-categorization.

    Compiles patterns once into rules and indexes. Domain rules are indexed
    in a dict for O(1) exact-match lookup; suffix-match domains use a
    separate list for short linear scans. Other rule types use ordered lists.
    """

    def __init__(self, categories: Dict[str, List[str]]):
        self.rules = []
        self._domain_exact: Dict[str, str] = {}
        self._domain_suffix: List[dict] = []
        self._path_rules: List[dict] = []
        self._ext_rules: List[dict] = []
        self._keyword_rules: List[dict] = []
        self._title_rules: List[dict] = []
        self._regex_rules: List[dict] = []
        self.compile_patterns(categories)

    def compile_patterns(self, categories: Dict[str, List[str]]):
        """Compile all patterns into rules and build indexes."""
        self.rules = []
        self._domain_exact = {}
        self._domain_suffix = []
        self._path_rules = []
        self._ext_rules = []
        self._keyword_rules = []
        self._title_rules = []
        self._regex_rules = []

        if not isinstance(categories, dict):
            return

        for category, patterns in categories.items():
            if isinstance(patterns, str):
                pattern_iterable: Iterable = [patterns]
            elif isinstance(patterns, Iterable):
                pattern_iterable = patterns
            else:
                continue

            for p in pattern_iterable:
                if not isinstance(p, str) or not p.strip():
                    continue
                rule = {"category": category, "raw": p}
                p_stripped = p.strip()
                p_lower = p_stripped.lower()

                try:
                    if p_lower.startswith("regex:"):
                        regex_str = p_stripped[6:]
                        if not regex_str or len(regex_str) > 500:
                            continue
                        rule["type"] = "regex"
                        rule["matcher"] = re.compile(regex_str, re.IGNORECASE)
                        self._regex_rules.append(rule)
                    elif p_lower.startswith("domain:"):
                        matcher = p_stripped[7:].lower().strip().rstrip(".").removeprefix("www.")
                        if not matcher:
                            continue
                        rule["type"] = "domain"
                        rule["matcher"] = matcher
                        if "." in matcher and not matcher.startswith("."):
                            if matcher not in self._domain_exact:
                                self._domain_exact[matcher] = category
                        self._domain_suffix.append(rule)
                    elif p_lower.startswith("path:"):
                        matcher = p_stripped[5:].lower().strip()
                        if not matcher:
                            continue
                        rule["type"] = "path"
                        rule["matcher"] = matcher
                        self._path_rules.append(rule)
                    elif p_lower.startswith("keyword:"):
                        matcher = p_stripped[8:].lower().strip()
                        if not matcher:
                            continue
                        rule["type"] = "keyword"
                        rule["matcher"] = matcher
                        self._keyword_rules.append(rule)
                    elif p_lower.startswith("title:"):
                        matcher = p_stripped[6:].lower().strip()
                        if not matcher:
                            continue
                        rule["type"] = "title"
                        rule["matcher"] = matcher
                        self._title_rules.append(rule)
                    elif p_lower.startswith("ext:"):
                        matcher = p_stripped[4:].lower().strip().lstrip(".")
                        if not matcher:
                            continue
                        rule["type"] = "extension"
                        rule["matcher"] = matcher
                        self._ext_rules.append(rule)
                    else:
                        continue
                    self.rules.append(rule)
                except re.error:
                    pass

    def match(self, url: str, title: str = "") -> Optional[str]:
        """Return the best matching category for the given URL/title, or None.

        Pass 1: O(1) exact domain lookup, then suffix domain scan, path, extension.
        Pass 2: keyword, title, regex (broader matching).
        """
        url_text = str(url or "")
        title_text = str(title or "")
        url_lower = url_text.lower()
        title_lower = title_text.lower()

        try:
            parse_target = url_text if "://" in url_text else f"https://{url_text}"
            parsed = urlparse(parse_target)
            domain = (parsed.hostname or "").lower().removeprefix("www.")
            path = parsed.path.lower()
        except Exception:
            domain = path = ""

        # Pass 1a: O(1) exact domain lookup
        if domain in self._domain_exact:
            return self._domain_exact[domain]

        # Pass 1b: suffix domain match (for patterns like "example.com" matching "sub.example.com")
        if domain:
            for rule in self._domain_suffix:
                matcher = rule["matcher"]
                try:
                    if domain.endswith("." + matcher):
                        return rule["category"]
                except Exception:
                    continue

        # Pass 1c: path rules
        if path:
            for rule in self._path_rules:
                try:
                    if rule["matcher"] in path:
                        return rule["category"]
                except Exception:
                    continue

        # Pass 1d: extension rules
        if path:
            for rule in self._ext_rules:
                try:
                    if path.endswith(f".{rule['matcher']}"):
                        return rule["category"]
                except Exception:
                    continue

        # Pass 2a: keyword rules
        for rule in self._keyword_rules:
            try:
                matcher = rule["matcher"]
                if matcher in url_lower or matcher in title_lower:
                    return rule["category"]
            except Exception:
                continue

        # Pass 2b: title rules
        for rule in self._title_rules:
            try:
                if rule["matcher"] in title_lower:
                    return rule["category"]
            except Exception:
                continue

        # Pass 2c: regex rules
        for rule in self._regex_rules:
            try:
                if _safe_regex_search(rule["matcher"], url_text) or _safe_regex_search(rule["matcher"], title_text):
                    return rule["category"]
            except Exception:
                continue

        return None
