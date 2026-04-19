"""Bookmark dataclass — the core entity of the application."""

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def _clean_tag_list(value) -> List[str]:
    """Normalize tag-like input while preserving first-seen casing."""
    if isinstance(value, str):
        raw_values = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_values = value
    else:
        return []

    cleaned = []
    seen = set()
    for item in raw_values:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        cleaned.append(text)
        seen.add(key)
    return cleaned


@dataclass
class Bookmark:
    """A single bookmark with all metadata.

    Attributes:
        id: Unique integer identifier (auto-generated via os.urandom)
        url: Bookmark URL
        title: Display title
        category: Category name
        parent_category: Parent category for nesting
        tags: User-applied tags
        ai_tags: AI-suggested tags
        notes: User notes
        description: AI-generated or user description
        created_at / modified_at / last_visited: ISO timestamps
        visit_count: Number of visits
        favicon_path / favicon_url / icon: Favicon storage
        is_valid: Whether URL validation passed
        is_pinned / is_archived: Status flags
        custom_data: Free-form metadata (e.g., redirect_url, _deleted_at)
    """

    id: Optional[int]
    url: str
    title: str
    category: str = "Uncategorized / Needs Review"
    parent_category: str = ""
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    description: str = ""
    created_at: str = ""
    modified_at: str = ""
    add_date: str = ""
    last_visited: str = ""
    visit_count: int = 0
    favicon_path: str = ""
    favicon_url: str = ""
    icon: str = ""
    screenshot_path: str = ""
    ai_confidence: float = 0.0
    ai_tags: List[str] = field(default_factory=list)
    source_file: str = ""
    last_checked: str = ""
    is_valid: bool = True
    http_status: int = 0
    is_pinned: bool = False
    is_archived: bool = False
    reading_time: int = 0
    word_count: int = 0
    language: str = ""
    custom_data: Dict = field(default_factory=dict)

    def __post_init__(self):
        if self.id is None:
            self.id = int.from_bytes(os.urandom(8), 'big')
        self.url = str(self.url or "").strip()
        if not self.url:
            raise ValueError("Bookmark URL is required")
        self.title = str(self.title or self.url)
        self.category = str(self.category or "Uncategorized / Needs Review")
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.modified_at:
            self.modified_at = self.created_at
        self.tags = _clean_tag_list(self.tags)
        self.ai_tags = _clean_tag_list(self.ai_tags)
        if not isinstance(self.custom_data, dict):
            self.custom_data = {}

    @property
    def domain(self) -> str:
        try:
            hostname = urlparse(self.url).hostname or ""
            return hostname.lower().removeprefix("www.")
        except Exception:
            return ""

    @property
    def display_title(self) -> str:
        return self.title[:100] if self.title else self.url[:50]

    @property
    def full_category_path(self) -> str:
        if self.parent_category:
            return f"{self.parent_category} / {self.category}"
        return self.category

    @property
    def age_days(self) -> int:
        try:
            created = datetime.fromisoformat(self.created_at.replace('Z', '+00:00'))
            return max(0, (datetime.now() - created.replace(tzinfo=None)).days)
        except Exception:
            return 0

    @property
    def is_stale(self) -> bool:
        """True if bookmark hasn't been visited in 90 days."""
        if not self.last_visited:
            return self.age_days > 90
        try:
            visited = datetime.fromisoformat(self.last_visited.replace('Z', '+00:00'))
            return (datetime.now() - visited.replace(tzinfo=None)).days > 90
        except Exception:
            return True

    def add_tag(self, tag: str):
        tag = str(tag or "").strip()
        if tag and tag.lower() not in {existing.lower() for existing in self.tags}:
            self.tags.append(tag)
            self.modified_at = datetime.now().isoformat()

    def remove_tag(self, tag: str):
        if tag in self.tags:
            self.tags.remove(tag)
            self.modified_at = datetime.now().isoformat()

    def record_visit(self):
        self.visit_count += 1
        self.last_visited = datetime.now().isoformat()
        self.modified_at = self.last_visited

    def clean_url(self) -> str:
        """URL with tracking parameters removed."""
        try:
            parsed = urlparse(self.url)
            params = parse_qs(parsed.query)
            tracking = {
                'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
                'fbclid', 'gclid', 'msclkid', 'ref', 'source', 'mc_cid', 'mc_eid',
                '_ga', '_gl', 'yclid', 'twclid', 'igshid'
            }
            cleaned = {k: v for k, v in params.items() if k.lower() not in tracking}
            return urlunparse((
                parsed.scheme, parsed.netloc, parsed.path,
                parsed.params, urlencode(cleaned, doseq=True), parsed.fragment
            ))
        except Exception:
            return self.url

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "url": self.url, "title": self.title,
            "category": self.category, "parent_category": self.parent_category,
            "tags": list(self.tags), "notes": self.notes, "description": self.description,
            "created_at": self.created_at, "modified_at": self.modified_at,
            "add_date": self.add_date, "last_visited": self.last_visited,
            "visit_count": self.visit_count, "favicon_path": self.favicon_path,
            "favicon_url": self.favicon_url, "icon": self.icon,
            "screenshot_path": self.screenshot_path, "ai_confidence": self.ai_confidence,
            "ai_tags": list(self.ai_tags), "source_file": self.source_file,
            "last_checked": self.last_checked, "is_valid": self.is_valid,
            "http_status": self.http_status, "is_pinned": self.is_pinned,
            "is_archived": self.is_archived, "reading_time": self.reading_time,
            "word_count": self.word_count, "language": self.language,
            "custom_data": dict(self.custom_data)
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "Bookmark":
        if not isinstance(d, dict):
            raise ValueError("Bookmark data must be an object")
        raw_url = d.get("url", "")
        if not isinstance(raw_url, str):
            raise ValueError("Bookmark URL must be a string")
        url = raw_url.strip()
        if not url:
            raise ValueError("Bookmark URL is required")

        # Defensive casts for fields that may arrive corrupted from JSON
        def safe_int(v, default=0):
            try:
                return max(0, int(v))
            except (TypeError, ValueError):
                return default

        def safe_float_01(v, default=0.0):
            try:
                return min(1.0, max(0.0, float(v)))
            except (TypeError, ValueError):
                return default

        def safe_optional_int(v):
            if v in (None, ""):
                return None
            try:
                value = int(v)
                return value if value > 0 else None
            except (TypeError, ValueError):
                return None

        def safe_bool(v, default=False):
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                normalized = v.strip().lower()
                if normalized in {"true", "1", "yes", "y", "on"}:
                    return True
                if normalized in {"false", "0", "no", "n", "off"}:
                    return False
            if isinstance(v, (int, float)):
                return bool(v)
            return default

        def safe_list(v):
            return _clean_tag_list(v)

        return cls(
            id=safe_optional_int(d.get("id")),
            url=url,
            title=str(d.get("title") or url),
            category=str(d.get("category") or "Uncategorized / Needs Review"),
            parent_category=str(d.get("parent_category") or ""),
            tags=safe_list(d.get("tags", [])),
            notes=str(d.get("notes") or ""),
            description=str(d.get("description") or ""),
            created_at=str(d.get("created_at") or ""),
            modified_at=str(d.get("modified_at") or ""),
            add_date=str(d.get("add_date") or ""),
            last_visited=str(d.get("last_visited") or ""),
            visit_count=safe_int(d.get("visit_count", 0)),
            favicon_path=str(d.get("favicon_path") or ""),
            favicon_url=str(d.get("favicon_url") or ""),
            icon=str(d.get("icon") or ""),
            screenshot_path=str(d.get("screenshot_path") or ""),
            ai_confidence=safe_float_01(d.get("ai_confidence", 0.0)),
            ai_tags=safe_list(d.get("ai_tags", [])),
            source_file=str(d.get("source_file") or ""),
            last_checked=str(d.get("last_checked") or ""),
            is_valid=safe_bool(d.get("is_valid", True), True),
            http_status=safe_int(d.get("http_status", 0)),
            is_pinned=safe_bool(d.get("is_pinned", False)),
            is_archived=safe_bool(d.get("is_archived", False)),
            reading_time=safe_int(d.get("reading_time", 0)),
            word_count=safe_int(d.get("word_count", 0)),
            language=str(d.get("language") or ""),
            custom_data=dict(d.get("custom_data")) if isinstance(d.get("custom_data"), dict) else {},
        )
