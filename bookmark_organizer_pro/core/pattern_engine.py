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
from collections.abc import Iterable
from typing import Dict, List, Optional
from urllib.parse import urlparse


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
        """Return the first matching category for the given URL/title, or None."""
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

        for rule in self.rules:
            matcher = rule["matcher"]
            rtype = rule["type"]

            try:
                if rtype == "domain" and (domain == matcher or domain.endswith("." + matcher)):
                    return rule["category"]
                elif rtype == "path" and matcher in path:
                    return rule["category"]
                elif rtype == "keyword" and (matcher in url_lower or matcher in title_lower):
                    return rule["category"]
                elif rtype == "title" and matcher in title_lower:
                    return rule["category"]
                elif rtype == "extension":
                    if path.endswith(f".{matcher}"):
                        return rule["category"]
                elif rtype == "regex":
                    if matcher.search(url_text) or matcher.search(title_text):
                        return rule["category"]
                elif rtype == "plain":
                    if matcher in domain or matcher in url_lower or matcher in title_lower:
                        return rule["category"]
            except Exception:
                continue

        return None
