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
            return cls(name="Unknown", patterns=d)
        return cls(
            name=d.get("name", ""),
            parent=d.get("parent", ""),
            patterns=d.get("patterns", []),
            icon=d.get("icon", "📁"),
            color=d.get("color", ""),
            description=d.get("description", ""),
            is_collapsed=d.get("is_collapsed", False),
            sort_order=d.get("sort_order", 0),
        )
