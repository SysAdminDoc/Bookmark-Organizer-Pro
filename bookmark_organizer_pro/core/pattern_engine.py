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
        for category, patterns in categories.items():
            for p in patterns:
                if not isinstance(p, str) or not p.strip():
                    continue
                rule = {"category": category, "raw": p}
                p_stripped = p.strip()

                try:
                    if p_stripped.startswith("regex:"):
                        regex_str = p_stripped[6:]
                        if len(regex_str) > 500:
                            continue  # Skip overly long regex (ReDoS guard)
                        rule["type"] = "regex"
                        rule["matcher"] = re.compile(regex_str, re.IGNORECASE)
                    elif p_stripped.startswith("domain:"):
                        rule["type"] = "domain"
                        rule["matcher"] = p_stripped[7:].lower().strip()
                    elif p_stripped.startswith("path:"):
                        rule["type"] = "path"
                        rule["matcher"] = p_stripped[5:].lower().strip()
                    elif p_stripped.startswith("keyword:"):
                        rule["type"] = "keyword"
                        rule["matcher"] = p_stripped[8:].lower().strip()
                    elif p_stripped.startswith("title:"):
                        rule["type"] = "title"
                        rule["matcher"] = p_stripped[6:].lower().strip()
                    elif p_stripped.startswith("ext:"):
                        rule["type"] = "extension"
                        rule["matcher"] = p_stripped[4:].lower().strip()
                    else:
                        rule["type"] = "plain"
                        rule["matcher"] = p_stripped.lower()
                    self.rules.append(rule)
                except re.error:
                    pass

    def match(self, url: str, title: str = "") -> Optional[str]:
        """Return the first matching category for the given URL/title, or None."""
        url_lower = url.lower()
        title_lower = (title or "").lower()

        try:
            parsed = urlparse(url)
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
                    if matcher.search(url) or matcher.search(title or ""):
                        return rule["category"]
                elif rtype == "plain":
                    if matcher in domain or matcher in url_lower or matcher in title_lower:
                        return rule["category"]
            except Exception:
                continue

        return None
