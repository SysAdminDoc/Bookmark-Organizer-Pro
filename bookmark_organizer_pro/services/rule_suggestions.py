"""Propose organization rules from the way a library is already filed.

The shipped pattern set cannot cover a personal library: employer intranets,
local council sites, and niche vendors are meaningless to everyone else, so
they stay uncategorized forever. Those domains are, however, perfectly visible
in the user's own filing decisions. Where every bookmark on one host already
sits in the same category, that is a rule the user has been applying by hand.

Proposals are plain data. They become real rules only through the existing
``OrganizationRulesService`` preview and apply path, which keeps the
allowlisted-predicate and undo guarantees intact.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from bookmark_organizer_pro.models import Bookmark

# Categories that mean "not filed yet" rather than a real decision.
PLACEHOLDER_CATEGORIES = frozenset({
    "", "imported", "uncategorized", "uncategorized / needs review", "other", "misc",
    "unsorted", "bookmarks bar", "bookmarks", "unfiled", "new folder",
})

DEFAULT_MIN_SUPPORT = 3
DEFAULT_MIN_AGREEMENT = 0.8


@dataclass(frozen=True)
class RuleSuggestion:
    """A proposed domain to category rule, with the evidence behind it."""

    domain: str
    category: str
    support: int
    total: int
    agreement: float
    examples: Tuple[str, ...] = ()
    competing: Tuple[Tuple[str, int], ...] = ()

    @property
    def name(self) -> str:
        return f"{self.domain} to {self.category}"

    def to_rule_document(self) -> Dict[str, Any]:
        """Shape this proposal as an OrganizationRule payload."""
        return {
            "name": self.name,
            "conditions": [{"field": "domain", "operator": "equals", "value": self.domain}],
            "actions": [{"action": "set_category", "value": self.category}],
            "enabled": True,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "category": self.category,
            "support": self.support,
            "total": self.total,
            "agreement": round(self.agreement, 3),
            "examples": list(self.examples),
            "competing": [{"category": name, "count": count} for name, count in self.competing],
        }


def _is_placeholder(category: str) -> bool:
    return str(category or "").strip().lower() in PLACEHOLDER_CATEGORIES


def _domain_of(bookmark: Bookmark) -> str:
    domain = str(getattr(bookmark, "domain", "") or "").strip().lower()
    if domain:
        return domain.removeprefix("www.")
    from urllib.parse import urlsplit

    try:
        host = (urlsplit(str(bookmark.url)).hostname or "").lower()
    except ValueError:
        return ""
    return host.removeprefix("www.")


def suggest_domain_category_rules(
    bookmarks: Iterable[Bookmark],
    *,
    min_support: int = DEFAULT_MIN_SUPPORT,
    min_agreement: float = DEFAULT_MIN_AGREEMENT,
    known_domains: Optional[Sequence[str]] = None,
    existing_rule_domains: Optional[Sequence[str]] = None,
) -> List[RuleSuggestion]:
    """Propose one rule per host whose filing is consistent enough to encode.

    ``known_domains`` are hosts the shipped pattern engine already routes, so
    proposing them would add a rule that changes nothing.
    """
    min_support = max(1, int(min_support))
    min_agreement = min(1.0, max(0.0, float(min_agreement)))
    skip = {str(d).strip().lower().removeprefix("www.") for d in (known_domains or ())}
    skip |= {str(d).strip().lower().removeprefix("www.") for d in (existing_rule_domains or ())}

    by_domain: Dict[str, Counter] = defaultdict(Counter)
    examples: Dict[Tuple[str, str], List[str]] = defaultdict(list)

    for bookmark in bookmarks:
        domain = _domain_of(bookmark)
        if not domain or domain in skip:
            continue
        category = str(getattr(bookmark, "category", "") or "").strip()
        if _is_placeholder(category):
            continue
        by_domain[domain][category] += 1
        bucket = examples[(domain, category)]
        if len(bucket) < 3:
            bucket.append(str(bookmark.url))

    suggestions: List[RuleSuggestion] = []
    for domain, counts in by_domain.items():
        total = sum(counts.values())
        category, support = counts.most_common(1)[0]
        if support < min_support:
            continue
        agreement = support / total if total else 0.0
        if agreement < min_agreement:
            continue
        competing = tuple(
            (name, count) for name, count in counts.most_common() if name != category
        )
        suggestions.append(RuleSuggestion(
            domain=domain,
            category=category,
            support=support,
            total=total,
            agreement=agreement,
            examples=tuple(examples[(domain, category)]),
            competing=competing,
        ))

    # Strongest evidence first, then alphabetically for a stable listing.
    suggestions.sort(key=lambda item: (-item.support, -item.agreement, item.domain))
    return suggestions


def shipped_pattern_domains() -> List[str]:
    """Domains the bundled pattern engine already routes."""
    from bookmark_organizer_pro.core.default_categories import DEFAULT_CATEGORIES

    domains: List[str] = []
    for patterns in DEFAULT_CATEGORIES.values():
        for pattern in patterns:
            if isinstance(pattern, str) and pattern.lower().startswith("domain:"):
                value = pattern[7:].strip().lower().strip(".")
                if value:
                    domains.append(value.removeprefix("www."))
    return domains


def existing_rule_domains(rules: Iterable[Any]) -> List[str]:
    """Domains already targeted by saved organization rules."""
    found: List[str] = []
    for rule in rules or ():
        for condition in getattr(rule, "conditions", ()) or ():
            if condition.get("field") == "domain" and condition.get("operator") == "equals":
                value = str(condition.get("value") or "").strip().lower()
                if value:
                    found.append(value.removeprefix("www."))
    return found
