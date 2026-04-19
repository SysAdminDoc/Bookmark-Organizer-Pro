"""Category manager with nesting, icon mapping, and pattern compilation."""

import json
import os
import tempfile
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


def _clean_patterns(patterns) -> List[str]:
    """Normalize a pattern collection while preserving first-seen order."""
    if isinstance(patterns, str):
        raw_patterns = [patterns]
    elif isinstance(patterns, (list, tuple, set)):
        raw_patterns = patterns
    else:
        return []

    cleaned = []
    seen = set()
    for pattern in raw_patterns:
        if pattern is None:
            continue
        text = str(pattern).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        cleaned.append(text)
        seen.add(key)
    return cleaned


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
                        normalized_name = str(name).strip()
                        if not normalized_name:
                            continue
                        if isinstance(data, list):
                            # Legacy format: {name: [patterns]}
                            self.categories[normalized_name] = Category(
                                name=normalized_name,
                                patterns=_clean_patterns(data),
                                icon=get_category_icon(normalized_name),
                            )
                        else:
                            cat = Category.from_dict(data)
                            cat.name = normalized_name
                            cat.patterns = _clean_patterns(cat.patterns)
                            if cat.parent == cat.name:
                                cat.parent = ""
                            self.categories[normalized_name] = cat
                else:
                    log.error(f"Invalid categories format in {self.filepath}; resetting to defaults")
                    self._init_defaults()
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

        self._repair_parent_links()
        self._rebuild_patterns()

    def _repair_parent_links(self):
        """Clear missing or cyclic parent links loaded from disk."""
        for name, cat in list(self.categories.items()):
            if cat.parent and cat.parent not in self.categories:
                log.warning(f"Clearing missing parent '{cat.parent}' from category '{name}'")
                cat.parent = ""

        for name, cat in list(self.categories.items()):
            seen = {name}
            current = cat.parent
            while current:
                if current in seen:
                    log.warning(f"Breaking category cycle at '{name}'")
                    cat.parent = ""
                    break
                seen.add(current)
                parent = self.categories.get(current)
                current = parent.parent if parent else ""

    def _init_defaults(self):
        """Initialize with the built-in default categories."""
        self.categories.clear()
        for name, patterns in self.DEFAULT_CATEGORIES.items():
            self.categories[name] = Category(
                name=name,
                patterns=_clean_patterns(patterns),
                icon=get_category_icon(name),
            )
        self.save_categories()

    def _rebuild_patterns(self):
        """Recompile the PatternEngine from current categories."""
        patterns_dict = {cat.full_path: _clean_patterns(cat.patterns) for cat in self.categories.values()}
        self.pattern_engine = PatternEngine(patterns_dict)

    def save_categories(self):
        """Persist categories to disk."""
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            data = {name: cat.to_dict() for name, cat in self.categories.items()}
            fd, temp_path = tempfile.mkstemp(
                dir=self.filepath.parent, suffix='.tmp', text=True
            )
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(temp_path, self.filepath)
            except Exception:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise
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
        normalized = (name or "").strip()
        parent = (parent or "").strip()
        if normalized and normalized not in self.categories:
            if parent and parent not in self.categories:
                return False
            cat = Category(
                name=normalized,
                parent=parent,
                patterns=_clean_patterns(patterns or []),
                icon=icon or get_category_icon(normalized),
            )
            self.categories[normalized] = cat
            self.save_categories()
            self._rebuild_patterns()
            return True
        return False

    def remove_category(self, name: str) -> bool:
        """Remove a category and its descendants."""
        if name in self.categories and "Uncategorized" not in name:
            for category_name in [name] + self.get_descendants(name):
                self.categories.pop(category_name, None)
            self.save_categories()
            self._rebuild_patterns()
            return True
        return False

    def rename_category(self, old_name: str, new_name: str) -> bool:
        """Rename a category and update all children's parent refs."""
        new_name = (new_name or "").strip()
        if (old_name in self.categories and new_name and new_name.strip() and
                new_name not in self.categories and "Uncategorized" not in old_name):
            cat = self.categories.pop(old_name)
            cat.name = new_name
            self.categories[new_name] = cat

            for child_cat in self.categories.values():
                if child_cat.parent == old_name:
                    child_cat.parent = new_name

            self.save_categories()
            self._rebuild_patterns()
            return True
        return False

    def move_category(self, name: str, new_parent: str) -> bool:
        """Reparent a category."""
        new_parent = (new_parent or "").strip()
        if name in self.categories and "Uncategorized" not in name:
            if new_parent and new_parent not in self.categories:
                return False
            if new_parent == name or self._is_descendant(new_parent, name):
                return False
            self.categories[name].parent = new_parent
            self.save_categories()
            self._rebuild_patterns()
            return True
        return False

    def _is_descendant(self, possible_child: str, parent: str) -> bool:
        """Return True if possible_child is already below parent in the tree."""
        seen = set()
        current = possible_child
        while current:
            if current == parent:
                return True
            if current in seen:
                return True
            seen.add(current)
            cat = self.categories.get(current)
            current = cat.parent if cat else ""
        return False

    def update_patterns(self, name: str, patterns: List[str]) -> bool:
        """Replace a category's patterns."""
        if name in self.categories:
            self.categories[name].patterns = _clean_patterns(patterns)
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
            return list(self.categories[name].patterns)
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

    def get_descendants(self, parent: str) -> List[str]:
        """Return all descendant category names below parent."""
        descendants = []
        stack = list(self.get_children(parent))
        seen = set()
        while stack:
            child = stack.pop()
            if child in seen:
                continue
            seen.add(child)
            descendants.append(child)
            stack.extend(self.get_children(child))
        return descendants

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
            if (
                source != target and
                "Uncategorized" not in source and
                not self._is_descendant(target, source)
            ):
                for cat in self.categories.values():
                    if cat.parent == source:
                        cat.parent = target

                self.categories[target].patterns = _clean_patterns(
                    self.categories[target].patterns + self.categories[source].patterns
                )
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
