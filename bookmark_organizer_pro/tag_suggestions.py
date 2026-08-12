"""Deterministic tag input and autocomplete rules shared by desktop surfaces."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from collections.abc import Iterable


_TAG_SEPARATOR_RE = re.compile(r"[,\n]")


def normalize_tag(value: object) -> str:
    """Return a display-safe tag while preserving user-entered casing."""

    if not isinstance(value, str):
        value = getattr(value, "full_path", getattr(value, "name", value))
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def tag_key(value: object) -> str:
    """Return the case-insensitive comparison key for a tag."""

    return normalize_tag(value).lower()


def unique_tags(values: Iterable[object] | object | None) -> list[str]:
    """Keep the first spelling of each non-empty tag, case-insensitively."""

    if values is None:
        return []
    if isinstance(values, str):
        values = parse_tag_input(values)
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = normalize_tag(value)
        key = tag_key(tag)
        if tag and key not in seen:
            seen.add(key)
            result.append(tag)
    return result


def parse_tag_input(value: object) -> list[str]:
    """Split pasted/comma-separated input into non-empty display tags."""

    return unique_tags(_TAG_SEPARATOR_RE.split(str(value or "")))


def current_tag_query(value: object) -> str:
    """Return the active token used to rank suggestions."""

    chunks = _TAG_SEPARATOR_RE.split(str(value or ""))
    return normalize_tag(chunks[-1] if chunks else "")


@dataclass(frozen=True)
class TagSuggestion:
    """A ranked suggestion with its stable comparison metadata."""

    value: str
    rank: int
    key: str


def rank_tag_suggestions(
    query: object,
    available_tags: Iterable[object] | object | None,
    selected_tags: Iterable[object] | object | None = None,
    limit: int = 8,
) -> list[str]:
    """Rank matching tags by relevance, then by stable Unicode order.

    Exact matches win over prefixes, token-prefix matches, and substrings. Empty
    input returns the shortest vocabulary entries first. The first spelling of a
    case-insensitive duplicate is retained and selected tags are excluded.
    """

    try:
        limit_value = max(1, min(50, int(limit)))
    except (TypeError, ValueError):
        limit_value = 8

    selected = {tag_key(value) for value in unique_tags(selected_tags)}
    query_text = normalize_tag(query)
    query_key = tag_key(query_text)
    candidates: list[TagSuggestion] = []
    for value in unique_tags(available_tags):
        key = tag_key(value)
        if key in selected:
            continue
        if not query_key:
            rank = 3
        elif key == query_key:
            rank = 0
        elif key.startswith(query_key):
            rank = 1
        elif any(token.startswith(query_key) for token in key.split()):
            rank = 2
        elif query_key in key:
            rank = 3
        else:
            continue
        candidates.append(TagSuggestion(value=value, rank=rank, key=key))

    candidates.sort(
        key=lambda item: (
            item.rank,
            len(item.key) if query_key else 0,
            item.key,
            item.value,
        )
    )
    return [item.value for item in candidates[:limit_value]]


__all__ = [
    "TagSuggestion",
    "current_tag_query",
    "normalize_tag",
    "parse_tag_input",
    "rank_tag_suggestions",
    "tag_key",
    "unique_tags",
]
