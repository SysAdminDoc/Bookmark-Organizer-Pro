"""Tag persistence and lookup manager."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from bookmark_organizer_pro.constants import TAGS_FILE
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Tag
from bookmark_organizer_pro.utils.runtime import atomic_json_write as _atomic_json_write


class TagManager:
    """
        Manages bookmark tags with persistence.
        
        Handles creating, updating, deleting, and persisting tags.
        Tags are stored in ~/.bookmark_organizer/tags.json.
        
        Attributes:
            tags: Dict mapping tag names to Tag objects
            tags_file: Path to tags storage file
        
        Methods:
            create_tag(name, color, description): Create new tag
            delete_tag(name): Remove a tag
            update_tag(name, **kwargs): Update tag properties
            get_tag(name): Get tag by name
            get_all_tags(): Get all tags as list
            get_popular_tags(limit): Get most-used tags
            search_tags(query): Search tags by name
            suggest_tags(text): AI-powered tag suggestions
        """
    
    def __init__(self, filepath: Path = TAGS_FILE):
        self.filepath = filepath
        self.tags: Dict[str, Tag] = {}
        self._load_tags()
    
    def _load_tags(self):
        """Load tags from file"""
        if self.filepath.exists():
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    tag_items = data.get("tags", [])
                elif isinstance(data, list):
                    tag_items = data
                else:
                    tag_items = []
                for tag_data in tag_items:
                    tag = Tag.from_dict(tag_data)
                    if not tag.name:
                        continue
                    self.tags[tag.full_path] = tag
            except Exception as e:
                log.error(f"Error loading tags: {e}")
    
    def save_tags(self):
        """Save tags to file"""
        data = {
            "version": 1,
            "tags": [tag.to_dict() for tag in self.tags.values()]
        }
        try:
            _atomic_json_write(self.filepath, data)
        except Exception as e:
            log.error(f"Error saving tags: {e}")
    
    def add_tag(self, name: str, color: str = "", parent: str = "") -> Optional[Tag]:
        """Add a new tag (validates name is non-empty)"""
        if not name or not str(name).strip():
            log.warning("Attempted to add tag with empty name")
            return None
        name = str(name).strip()[:50]  # Cap length
        tag = Tag(name=name, color=str(color or "").strip(), parent=str(parent or "").strip())
        if tag.full_path in self.tags:
            return self.tags[tag.full_path]  # Return existing instead of duplicate
        self.tags[tag.full_path] = tag
        self.save_tags()
        return tag
    
    def remove_tag(self, tag_path: str) -> bool:
        """Remove a tag"""
        if tag_path in self.tags:
            del self.tags[tag_path]
            self.save_tags()
            return True
        return False
    
    def get_tag(self, tag_path: str) -> Optional[Tag]:
        """Get a tag by path"""
        return self.tags.get(tag_path)
    
    def get_all_tags(self) -> List[Tag]:
        """Get all tags sorted by name"""
        return sorted(self.tags.values(), key=lambda t: t.full_path.lower())
    
    def get_root_tags(self) -> List[Tag]:
        """Get tags without parents"""
        return [t for t in self.tags.values() if not t.parent]
    
    def get_child_tags(self, parent: str) -> List[Tag]:
        """Get child tags of a parent"""
        return [t for t in self.tags.values() if t.parent == parent]
    
    def search_tags(self, query: str) -> List[Tag]:
        """Search tags by name"""
        query = str(query or "").lower()
        return [t for t in self.tags.values() if query in t.name.lower()]
    
    def update_tag_color(self, tag_path: str, color: str) -> bool:
        """Update tag color"""
        if tag_path in self.tags:
            self.tags[tag_path].color = color
            self.save_tags()
            return True
        return False
    
    def merge_tags(self, source_path: str, target_path: str) -> bool:
        """Merge source tag into target (for bookmark manager to handle)"""
        if source_path in self.tags and target_path in self.tags:
            # Just remove the source tag, bookmarks need to be updated separately
            del self.tags[source_path]
            self.save_tags()
            return True
        return False
    
    def get_tag_suggestions(self, partial: str, limit: int = 10) -> List[str]:
        """Get tag suggestions for autocomplete"""
        partial = str(partial or "").lower()
        try:
            limit = max(1, min(100, int(limit)))
        except (TypeError, ValueError):
            limit = 10
        matches = [t.full_path for t in self.tags.values() 
                   if partial in t.name.lower()]
        return sorted(matches)[:limit]
