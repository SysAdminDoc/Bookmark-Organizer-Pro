"""Pattern engine for URL/title-based auto-categorization.

Supports multiple pattern types:
- domain:example.com     — exact or suffix domain match
- path:/some/path        — URL path substring match
- keyword:foo            — substring match in URL or title
- title:foo              — substring match in title only
- ext:pdf                — file extension match
- regex:pattern          — regex match against URL or title
- (plain)                — substring match in URL, domain, or title
"""

import re
import signal
import sys
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

    Compiles patterns once into rules; each match() call iterates the rules
    in definition order and returns the first matching category.
    """

    def __init__(self, categories: Dict[str, List[str]]):
        self.rules = []
        self.compile_patterns(categories)

    def compile_patterns(self, categories: Dict[str, List[str]]):
        """Compile all patterns into rules."""
        self.rules = []
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
                            continue  # Skip overly long regex (ReDoS guard)
                        rule["type"] = "regex"
                        rule["matcher"] = re.compile(regex_str, re.IGNORECASE)
                    elif p_lower.startswith("domain:"):
                        matcher = p_stripped[7:].lower().strip().rstrip(".").removeprefix("www.")
                        if not matcher:
                            continue
                        rule["type"] = "domain"
                        rule["matcher"] = matcher
                    elif p_lower.startswith("path:"):
                        matcher = p_stripped[5:].lower().strip()
                        if not matcher:
                            continue
                        rule["type"] = "path"
                        rule["matcher"] = matcher
                    elif p_lower.startswith("keyword:"):
                        matcher = p_stripped[8:].lower().strip()
                        if not matcher:
                            continue
                        rule["type"] = "keyword"
                        rule["matcher"] = matcher
                    elif p_lower.startswith("title:"):
                        matcher = p_stripped[6:].lower().strip()
                        if not matcher:
                            continue
                        rule["type"] = "title"
                        rule["matcher"] = matcher
                    elif p_lower.startswith("ext:"):
                        matcher = p_stripped[4:].lower().strip().lstrip(".")
                        if not matcher:
                            continue
                        rule["type"] = "extension"
                        rule["matcher"] = matcher
                    else:
                        matcher = p_stripped.lower()
                        if not matcher:
                            continue
                        rule["type"] = "plain"
                        rule["matcher"] = matcher
                    self.rules.append(rule)
                except re.error:
                    pass

    def match(self, url: str, title: str = "") -> Optional[str]:
        """Return the best matching category for the given URL/title, or None.

        Uses a two-pass priority system: domain and path rules (most specific)
        are checked first across ALL categories before falling back to keyword,
        title, regex, and extension rules. This prevents a generic keyword like
        "community" from overriding an exact domain match like "figma.com".
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

        # Pass 1: domain and path rules (highest specificity)
        for rule in self.rules:
            matcher = rule["matcher"]
            rtype = rule["type"]
            try:
                if rtype == "domain" and (domain == matcher or domain.endswith("." + matcher)):
                    return rule["category"]
                elif rtype == "path" and matcher in path:
                    return rule["category"]
                elif rtype == "extension" and path.endswith(f".{matcher}"):
                    return rule["category"]
            except Exception:
                continue

        # Pass 2: keyword, title, regex rules (broader matching)
        for rule in self.rules:
            matcher = rule["matcher"]
            rtype = rule["type"]
            try:
                if rtype == "keyword" and (matcher in url_lower or matcher in title_lower):
                    return rule["category"]
                elif rtype == "title" and matcher in title_lower:
                    return rule["category"]
                elif rtype == "regex":
                    if _safe_regex_search(matcher, url_text) or _safe_regex_search(matcher, title_text):
                        return rule["category"]
            except Exception:
                continue

        return None
