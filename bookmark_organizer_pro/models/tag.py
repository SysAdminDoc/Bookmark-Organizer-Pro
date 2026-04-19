"""Tag dataclass — flat or hierarchical labels for bookmarks."""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict


# Preset colors for auto-generated tag colors (consistent per tag name)
_TAG_COLORS = [
    "#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#a855f7",
    "#06b6d4", "#ec4899", "#f97316", "#84cc16", "#6366f1",
]


@dataclass
class Tag:
    """A bookmark tag.

    Attributes:
        name: Tag name (unique)
        color: Hex color (auto-generated from name if blank)
        icon: Optional icon
        parent: Parent tag for hierarchical tags like "dev/python"
        created_at: ISO timestamp
        bookmark_count: Cached count of bookmarks using this tag
    """

    name: str
    color: str = ""
    icon: str = ""
    parent: str = ""
    created_at: str = ""
    bookmark_count: int = 0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.color:
            self.color = self._generate_color()

    def _generate_color(self) -> str:
        """Generate a consistent color based on the tag name."""
        hash_val = sum(ord(c) for c in self.name)
        return _TAG_COLORS[hash_val % len(_TAG_COLORS)]

    @property
    def full_path(self) -> str:
        if self.parent:
            return f"{self.parent}/{self.name}"
        return self.name

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "color": self.color,
            "icon": self.icon,
            "parent": self.parent,
            "created_at": self.created_at,
            "bookmark_count": self.bookmark_count,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "Tag":
        if not isinstance(d, dict):
            d = {}

        def safe_str(value, default=""):
            return str(value).strip() if value not in (None, "") else default

        def safe_count(value):
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                return 0

        return cls(
            name=safe_str(d.get("name")),
            color=safe_str(d.get("color")),
            icon=safe_str(d.get("icon")),
            parent=safe_str(d.get("parent")),
            created_at=safe_str(d.get("created_at")),
            bookmark_count=safe_count(d.get("bookmark_count", 0)),
        )
