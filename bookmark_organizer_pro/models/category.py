"""Category dataclass — hierarchical organization for bookmarks."""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Category:
    """A bookmark category with optional nesting.

    Attributes:
        name: Category name (unique within parent)
        parent: Parent category name for nesting
        patterns: URL/keyword patterns that auto-match to this category
        icon: Emoji for display
        color: Optional color override
        description: Optional description
        is_collapsed: UI collapse state
        sort_order: Order within parent
    """

    name: str
    parent: str = ""
    patterns: List[str] = field(default_factory=list)
    icon: str = "📁"
    color: str = ""
    description: str = ""
    is_collapsed: bool = False
    sort_order: int = 0

    @property
    def full_path(self) -> str:
        if self.parent:
            return f"{self.parent} / {self.name}"
        return self.name

    @property
    def depth(self) -> int:
        return self.full_path.count(" / ")

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "parent": self.parent,
            "patterns": self.patterns,
            "icon": self.icon,
            "color": self.color,
            "description": self.description,
            "is_collapsed": self.is_collapsed,
            "sort_order": self.sort_order,
        }

    @classmethod
    def from_dict(cls, d) -> "Category":
        if isinstance(d, list):
            # Legacy format: just a pattern list
            return cls(
                name="Unknown",
                patterns=[str(p).strip() for p in d if p is not None and str(p).strip()]
            )
        if not isinstance(d, dict):
            return cls(name="Unknown")

        def safe_str(value, default=""):
            return str(value).strip() if value not in (None, "") else default

        def safe_patterns(value):
            if not isinstance(value, list):
                return []
            return [str(p).strip() for p in value if p is not None and str(p).strip()]

        def safe_bool(value, default=False):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"true", "1", "yes", "y", "on"}:
                    return True
                if normalized in {"false", "0", "no", "n", "off"}:
                    return False
            if isinstance(value, (int, float)):
                return bool(value)
            return default

        def safe_int(value, default=0):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        return cls(
            name=safe_str(d.get("name")),
            parent=safe_str(d.get("parent")),
            patterns=safe_patterns(d.get("patterns", [])),
            icon=safe_str(d.get("icon"), "📁"),
            color=safe_str(d.get("color")),
            description=safe_str(d.get("description")),
            is_collapsed=safe_bool(d.get("is_collapsed", False)),
            sort_order=safe_int(d.get("sort_order", 0)),
        )
