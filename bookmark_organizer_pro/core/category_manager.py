"""Category manager with nesting, icon mapping, and pattern compilation."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..constants import CATEGORIES_FILE
from ..logging_config import log
from ..models import Category
from .default_categories import DEFAULT_CATEGORIES
from .pattern_engine import PatternEngine


# Category name keyword → icon mapping (substring match, longest first wins)
CATEGORY_ICONS = {
    "uncategorized": "📥",
    "development": "💻",
    "programming": "💻",
    "ai": "🤖",
    "machine learning": "🤖",
    "news": "📰",
    "shopping": "🛒",
    "entertainment": "🎬",
    "social": "👥",
    "forum": "💬",
    "communit": "💬",
    "reference": "📚",
    "documentation": "📚",
    "finance": "💰",
    "banking": "🏦",
    "health": "🏥",
    "medical": "🏥",
    "travel": "✈️",
    "food": "🍔",
    "dining": "🍔",
    "music": "🎵",
    "audio": "🎵",
    "video": "🎥",
    "gaming": "🎮",
    "education": "🎓",
    "learning": "🎓",
    "science": "🔬",
    "sports": "⚽",
    "art": "🎨",
    "design": "🎨",
    "media production": "🎬",
    "security": "🔒",
    "privacy": "🔒",
    "tools": "🔧",
    "utilities": "🔧",
    "productivity": "📋",
    "cloud": "☁️",
    "infrastructure": "☁️",
    "database": "🗄️",
    "api": "🔌",
    "mobile": "📱",
    "work": "💼",
    "career": "💼",
    "job": "💼",
    "personal": "👤",
    "bookmarks": "🔖",
    "reading": "📖",
    "research": "🔍",
    "weather": "🌦️",
    "meteorolog": "🌦️",
    "sysadmin": "🖥️",
    "download": "📥",
    "torrent": "📥",
    "software": "💿",
    "customiz": "🎨",
    "adult": "🔞",
    "mature": "🔞",
    "redirect": "🔀",
    "tracker": "🔀",
    "shortener": "🔀",
    "internal": "🏠",
    "homelab": "🏠",
    "self-hosted": "🏠",
    "real estate": "🏘️",
    "automotive": "🚗",
    "government": "🏛️",
    "legal": "🏛️",
    "streaming": "📡",
}


def get_category_icon(category_name: str) -> str:
    """Return an emoji icon for a category name based on keyword match."""
    name_lower = (category_name or "").lower()
    for keyword, icon in CATEGORY_ICONS.items():
        if keyword in name_lower:
            return icon
    return "📂"


class CategoryManager:
    """Manages bookmark categories with hierarchy support.

    - Auto-loads from disk on init, falls back to DEFAULT_CATEGORIES
    - Rebuilds the PatternEngine whenever categories change
    - Supports nesting, renaming, moving, merging
    """

    DEFAULT_CATEGORIES = DEFAULT_CATEGORIES

    def __init__(self, filepath: Path = CATEGORIES_FILE):
        self.filepath = filepath
        self.categories: Dict[str, Category] = {}
        self.pattern_engine: Optional[PatternEngine] = None
        self._load_categories()

    def _load_categories(self):
        """Load categories from disk, or initialize defaults."""
        if self.filepath.exists():
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    raw = json.load(f)

                if isinstance(raw, dict):
                    for name, data in raw.items():
                        if isinstance(data, list):
                            # Legacy format: {name: [patterns]}
                            self.categories[name] = Category(
                                name=name,
                                patterns=data,
                                icon=get_category_icon(name),
                            )
                        else:
                            cat = Category.from_dict(data)
                            cat.name = name
                            self.categories[name] = cat
            except Exception as e:
                log.error(f"Error loading categories, resetting to defaults: {e}")
                self._init_defaults()
        else:
            self._init_defaults()

        # Always ensure uncategorized exists
        if "Uncategorized / Needs Review" not in self.categories:
            self.categories["Uncategorized / Needs Review"] = Category(
                name="Uncategorized / Needs Review",
                icon="📥",
            )

        self._rebuild_patterns()

    def _init_defaults(self):
        """Initialize with the built-in default categories."""
        for name, patterns in self.DEFAULT_CATEGORIES.items():
            self.categories[name] = Category(
                name=name,
                patterns=patterns,
                icon=get_category_icon(name),
            )
        self.save_categories()

    def _rebuild_patterns(self):
        """Recompile the PatternEngine from current categories."""
        patterns_dict = {cat.full_path: cat.patterns for cat in self.categories.values()}
        self.pattern_engine = PatternEngine(patterns_dict)

    def save_categories(self):
        """Persist categories to disk."""
        try:
            data = {name: cat.to_dict() for name, cat in self.categories.items()}
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.error(f"Error saving categories: {e}")

    def categorize_url(self, url: str, title: str = "") -> str:
        """Auto-categorize a URL, defaulting to 'Uncategorized / Needs Review'."""
        if self.pattern_engine:
            result = self.pattern_engine.match(url, title)
            if result:
                return result
        return "Uncategorized / Needs Review"

    def add_category(self, name: str, parent: str = "",
                     patterns: List[str] = None, icon: str = "") -> bool:
        """Add a new category."""
        if name and name.strip() and name not in self.categories:
            cat = Category(
                name=name.strip(),
                parent=parent,
                patterns=patterns or [],
                icon=icon or get_category_icon(name),
            )
            self.categories[name.strip()] = cat
            self.save_categories()
            self._rebuild_patterns()
            return True
        return False

    def remove_category(self, name: str) -> bool:
        """Remove a category and its descendants."""
        if name in self.categories and "Uncategorized" not in name:
            children = self.get_children(name)
            for child in children:
                self.categories.pop(child, None)
            del self.categories[name]
            self.save_categories()
            self._rebuild_patterns()
            return True
        return False

    def rename_category(self, old_name: str, new_name: str) -> bool:
        """Rename a category and update all children's parent refs."""
        if (old_name in self.categories and new_name and new_name.strip() and
                new_name not in self.categories and "Uncategorized" not in old_name):
            cat = self.categories.pop(old_name)
            cat.name = new_name.strip()
            self.categories[new_name.strip()] = cat

            for child_cat in self.categories.values():
                if child_cat.parent == old_name:
                    child_cat.parent = new_name.strip()

            self.save_categories()
            self._rebuild_patterns()
            return True
        return False

    def move_category(self, name: str, new_parent: str) -> bool:
        """Reparent a category."""
        if name in self.categories and "Uncategorized" not in name:
            if new_parent and new_parent not in self.categories:
                return False
            self.categories[name].parent = new_parent
            self.save_categories()
            return True
        return False

    def update_patterns(self, name: str, patterns: List[str]) -> bool:
        """Replace a category's patterns."""
        if name in self.categories:
            self.categories[name].patterns = patterns
            self.save_categories()
            self._rebuild_patterns()
            return True
        return False

    def update_icon(self, name: str, icon: str) -> bool:
        """Change a category's icon."""
        if name in self.categories:
            self.categories[name].icon = icon
            self.save_categories()
            return True
        return False

    def update_color(self, name: str, color: str) -> bool:
        """Change a category's color."""
        if name in self.categories:
            self.categories[name].color = color
            self.save_categories()
            return True
        return False

    def get_patterns(self, name: str) -> List[str]:
        if name in self.categories:
            return self.categories[name].patterns
        return []

    def get_category(self, name: str) -> Optional[Category]:
        return self.categories.get(name)

    def get_root_categories(self) -> List[Category]:
        """Top-level (un-parented) categories, sorted by sort_order then name."""
        return sorted(
            [c for c in self.categories.values() if not c.parent],
            key=lambda x: (x.sort_order, x.name.lower()),
        )

    def get_children(self, parent: str) -> List[str]:
        return [c.name for c in self.categories.values() if c.parent == parent]

    def get_sorted_categories(self) -> List[str]:
        """Alphabetically sorted with 'Uncategorized' last."""
        uncategorized = [c for c in self.categories if "Uncategorized" in c]
        regular = sorted([c for c in self.categories if "Uncategorized" not in c])
        return regular + uncategorized

    def get_all_categories(self) -> List[str]:
        return list(self.categories.keys())

    def get_tree(self) -> List[Tuple[Category, int]]:
        """Flat list of (category, depth) pairs in tree order."""
        result = []

        def visit(cat: Category, depth: int):
            result.append((cat, depth))
            children = sorted(
                [c for c in self.categories.values() if c.parent == cat.name],
                key=lambda x: (x.sort_order, x.name.lower()),
            )
            for child in children:
                visit(child, depth + 1)

        for root in self.get_root_categories():
            visit(root, 0)

        return result

    def merge_categories(self, source: str, target: str) -> bool:
        """Merge source into target: move children, combine patterns, delete source."""
        if source in self.categories and target in self.categories:
            if source != target and "Uncategorized" not in source:
                for cat in self.categories.values():
                    if cat.parent == source:
                        cat.parent = target

                self.categories[target].patterns.extend(self.categories[source].patterns)
                del self.categories[source]
                self.save_categories()
                self._rebuild_patterns()
                return True
        return False

    def toggle_collapsed(self, name: str) -> bool:
        """Toggle the UI collapse state of a category."""
        if name in self.categories:
            self.categories[name].is_collapsed = not self.categories[name].is_collapsed
            self.save_categories()
            return True
        return False
