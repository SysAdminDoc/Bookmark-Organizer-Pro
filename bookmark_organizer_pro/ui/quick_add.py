"""Quick-add form normalization and validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

from bookmark_organizer_pro.utils.validators import validate_url


DEFAULT_CATEGORY = "Uncategorized / Needs Review"
TITLE_PLACEHOLDER = "Title (optional)"
FAVICON_PLACEHOLDER = "Favicon URL or local image path"
SUPPORTED_BOOKMARK_SCHEMES = ("http://", "https://")


@dataclass(frozen=True)
class QuickAddPayload:
    """Normalized result from the quick-add form."""

    url: str
    title: str
    category: str
    favicon_input: str = ""

    def to_dict(self, custom_favicon: str = "") -> Dict[str, str]:
        return {
            "url": self.url,
            "title": self.title,
            "category": self.category,
            "custom_favicon": custom_favicon,
        }


def pick_default_category(categories: Sequence[str]) -> str:
    """Pick the safest category default for the quick-add dialog."""
    categories = [str(category).strip() for category in (categories or []) if str(category).strip()]
    if DEFAULT_CATEGORY in categories:
        return DEFAULT_CATEGORY
    return categories[0] if categories else DEFAULT_CATEGORY


def prepare_quick_add_payload(
    *,
    url: str,
    title: str = "",
    category: str = "",
    categories: Optional[Sequence[str]] = None,
    favicon_input: str = "",
    title_placeholder_active: bool = False,
    favicon_placeholder_active: bool = False,
) -> Tuple[Optional[QuickAddPayload], str]:
    """Normalize quick-add fields and return either a payload or an error."""
    normalized_url = normalize_bookmark_url(url)
    if not normalized_url:
        return None, "Enter a bookmark URL before adding it."

    valid, error = validate_url(normalized_url)
    if not valid or not normalized_url.startswith(SUPPORTED_BOOKMARK_SCHEMES):
        return None, error or "Enter an http:// or https:// bookmark URL."

    clean_title = "" if title_placeholder_active else str(title or "").strip()
    if clean_title == TITLE_PLACEHOLDER:
        clean_title = ""

    clean_favicon = "" if favicon_placeholder_active else str(favicon_input or "").strip()
    if clean_favicon == FAVICON_PLACEHOLDER:
        clean_favicon = ""

    return QuickAddPayload(
        url=normalized_url,
        title=clean_title or normalized_url,
        category=str(category or "").strip() or pick_default_category(categories or []),
        favicon_input=clean_favicon,
    ), ""


def normalize_bookmark_url(url: str) -> str:
    """Add a web scheme to bare domains without hiding malformed input."""
    value = str(url or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = f"https://{value}"
    return value
