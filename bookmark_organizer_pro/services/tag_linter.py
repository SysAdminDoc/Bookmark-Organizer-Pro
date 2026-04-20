"""Tag normalization linter.

Detects near-duplicate tags ("python" vs "Python" vs "python3" vs "py"),
casing/separator drift, and singular/plural variants. Surfaces a review
queue with suggested merges; never auto-merges without consent.

Goes beyond Karakeep's enforcement-only approach by working retrospectively
on already-imported tag chaos.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark


SEPARATORS = re.compile(r"[\s_\-\.]+")

PLURAL_SUFFIXES = ("s", "es", "ies")

CANONICAL_ALIASES = {
    "py": "python", "py3": "python", "python3": "python",
    "js": "javascript", "node": "nodejs", "node-js": "nodejs",
    "ts": "typescript",
    "k8s": "kubernetes",
    "ml": "machine-learning", "ai": "artificial-intelligence",
    "css3": "css", "html5": "html",
    "github-com": "github",
}


@dataclass
class TagSuggestion:
    canonical: str
    variants: List[str]
    bookmark_count: int

    def describe(self) -> str:
        v = ", ".join(self.variants)
        return f"{v} → {self.canonical}  ({self.bookmark_count} bookmarks)"


@dataclass
class LintReport:
    suggestions: List[TagSuggestion] = field(default_factory=list)
    total_tags: int = 0
    total_bookmarks: int = 0
    casing_drift: int = 0
    plural_drift: int = 0
    alias_collisions: int = 0


def _slug(s: str) -> str:
    s = s.strip().lower()
    s = SEPARATORS.sub("-", s)
    return CANONICAL_ALIASES.get(s, s)


def _depluralize(s: str) -> str:
    for suf in PLURAL_SUFFIXES:
        if len(s) > len(suf) + 2 and s.endswith(suf):
            stem = s[: -len(suf)]
            if suf == "ies":
                stem += "y"
            return stem
    return s


class TagLinter:
    """Build a lint report over a bookmark collection."""

    def lint(self, bookmarks: Iterable[Bookmark]) -> LintReport:
        report = LintReport()
        # tag -> set of bookmark IDs
        tag_buckets: Dict[str, Set[int]] = defaultdict(set)
        # canonical_key -> {raw_tag: count}
        groups: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        bookmark_count = 0

        for bm in bookmarks:
            bookmark_count += 1
            for raw in list(bm.tags) + list(bm.ai_tags):
                if not raw or not raw.strip():
                    continue
                slug = _slug(raw)
                key = _depluralize(slug)
                groups[key][raw].add if False else None  # noqa
                groups[key][raw] = groups[key].get(raw, 0) + 1
                tag_buckets[raw].add(bm.id)

        report.total_tags = sum(len(v) for v in groups.values())
        report.total_bookmarks = bookmark_count

        for canonical_key, variants_map in groups.items():
            if len(variants_map) <= 1:
                continue
            variants = sorted(variants_map.keys(), key=lambda v: (-variants_map[v], v))
            # Pick canonical: prefer the literal canonical key if any
            # variant matches it as-is (lowercase, no separators), otherwise
            # the most common variant.
            canonical = None
            for v in variants:
                if v == canonical_key or v.lower() == canonical_key:
                    canonical = v
                    break
            if canonical is None:
                canonical = variants[0]
            others = [v for v in variants if v != canonical]
            unique_bookmarks = set()
            for v in variants:
                unique_bookmarks.update(tag_buckets.get(v, set()))
            report.suggestions.append(TagSuggestion(
                canonical=canonical,
                variants=others,
                bookmark_count=len(unique_bookmarks),
            ))
            # Drift counters
            if len({v.lower() for v in variants}) < len(variants):
                report.casing_drift += 1
            for v in variants:
                if _depluralize(_slug(v)) != _slug(v):
                    report.plural_drift += 1
                    break
            if any(_slug(v) in CANONICAL_ALIASES for v in variants):
                report.alias_collisions += 1

        report.suggestions.sort(key=lambda s: s.bookmark_count, reverse=True)
        return report

    def apply(self, bookmarks: Iterable[Bookmark],
              suggestions: Iterable[TagSuggestion]) -> int:
        """Apply selected suggestions to the bookmark collection.

        Returns the number of bookmarks changed.
        """
        suggestion_map: Dict[str, str] = {}
        for s in suggestions:
            for v in s.variants:
                suggestion_map[v] = s.canonical
        if not suggestion_map:
            return 0

        changed = 0
        for bm in bookmarks:
            new_tags: List[str] = []
            seen: Set[str] = set()
            replaced = False
            for tag in bm.tags:
                target = suggestion_map.get(tag, tag)
                if target != tag:
                    replaced = True
                key = target.lower()
                if key in seen:
                    continue
                new_tags.append(target)
                seen.add(key)
            if replaced:
                bm.tags = new_tags
                changed += 1
        return changed
