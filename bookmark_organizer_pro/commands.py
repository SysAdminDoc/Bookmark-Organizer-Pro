"""Undo/redo command objects for bookmark mutations."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from bookmark_organizer_pro.models import Bookmark


class Command:
    """Base command for undo/redo system"""
    def execute(self): raise NotImplementedError
    def undo(self): raise NotImplementedError
    def description(self) -> str: return "Unknown"
    def can_merge(self, other: 'Command') -> bool: return False
    def merge(self, other: 'Command'): pass


class CommandStack:
    """
        Manages undo/redo functionality.
        
        Implements command pattern for reversible operations
        with support for command merging.
        
        Attributes:
            undo_stack: List of executed commands
            redo_stack: List of undone commands
            max_size: Maximum stack size (default: 50)
        
        Methods:
            execute(command): Execute and push to undo stack
            undo(): Undo last command
            redo(): Redo last undone command
            can_undo(): Check if undo available
            can_redo(): Check if redo available
            clear(): Clear all history
        
        Supported Commands:
            - MoveBookmarksCommand
            - DeleteBookmarksCommand
            - AddBookmarksCommand
            - BulkCategorizeCommand
            - TagBookmarksCommand
        """
    
    def __init__(self, max_history: int = 100):
        self._undo_stack: List[Command] = []
        self._redo_stack: List[Command] = []
        try:
            self._max_history = max(1, min(1000, int(max_history)))
        except (TypeError, ValueError):
            self._max_history = 100
        self._last_command_time = 0
        self._merge_window_ms = 500
    
    def execute(self, command: Command):
        """Execute a command and add to history"""
        if not isinstance(command, Command):
            raise TypeError("command must be a Command")
        command.execute()
        now = time.time() * 1000
        
        if (self._undo_stack and 
            now - self._last_command_time < self._merge_window_ms and
            self._undo_stack[-1].can_merge(command)):
            self._undo_stack[-1].merge(command)
        else:
            self._undo_stack.append(command)
        
        self._last_command_time = now
        self._redo_stack.clear()
        
        while len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)
    
    def undo(self) -> Optional[str]:
        """Undo the last command"""
        if not self._undo_stack:
            return None
        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)
        return command.description()
    
    def redo(self) -> Optional[str]:
        """Redo the last undone command"""
        if not self._redo_stack:
            return None
        command = self._redo_stack.pop()
        command.execute()
        self._undo_stack.append(command)
        return command.description()
    
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0
    
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0
    
    def clear(self):
        self._undo_stack.clear()
        self._redo_stack.clear()


class MoveBookmarksCommand(Command):
    """Command to move bookmarks to a category"""
    
    def __init__(self, manager, bookmark_ids: List[int], new_category: str):
        self.manager = manager
        self.ids = self._clean_ids(bookmark_ids)
        self.new_category = str(new_category or "").strip() or "Uncategorized / Needs Review"
        self.previous_categories: Dict[int, str] = {}

    @staticmethod
    def _clean_ids(bookmark_ids) -> List[int]:
        ids = []
        for bid in bookmark_ids or []:
            try:
                normalized = int(bid)
            except (TypeError, ValueError):
                continue
            if normalized not in ids:
                ids.append(normalized)
        return ids
    
    def execute(self):
        for bid in self.ids:
            bm = self.manager.bookmarks.get(bid)
            if bm:
                self.previous_categories[bid] = bm.category
                bm.category = self.new_category
                bm.modified_at = datetime.now().isoformat()
        self.manager.save_bookmarks()
    
    def undo(self):
        for bid, old_cat in self.previous_categories.items():
            bm = self.manager.bookmarks.get(bid)
            if bm:
                bm.category = old_cat
                bm.modified_at = datetime.now().isoformat()
        self.manager.save_bookmarks()
    
    def description(self) -> str:
        return f"Move {len(self.ids)} bookmark(s) to {self.new_category}"
    
    def can_merge(self, other: Command) -> bool:
        return isinstance(other, MoveBookmarksCommand) and other.new_category == self.new_category
    
    def merge(self, other: 'MoveBookmarksCommand'):
        for bid, cat in other.previous_categories.items():
            if bid not in self.previous_categories:
                self.previous_categories[bid] = cat
        self.ids = list(set(self.ids + other.ids))


class DeleteBookmarksCommand(Command):
    """Command to delete bookmarks"""
    
    def __init__(self, manager, bookmark_ids: List[int]):
        self.manager = manager
        self.ids = MoveBookmarksCommand._clean_ids(bookmark_ids)
        self.deleted_bookmarks: Dict[int, Bookmark] = {}
    
    def execute(self):
        self.deleted_bookmarks = {}
        for bid in self.ids:
            bm = self.manager.bookmarks.get(bid)
            if bm:
                # Store a copy (not a reference) so undo restores correct state
                self.deleted_bookmarks[bid] = Bookmark.from_dict(bm.to_dict())
                del self.manager.bookmarks[bid]
        self.manager.save_bookmarks()

    def undo(self):
        for bid, bm in self.deleted_bookmarks.items():
            if bid not in self.manager.bookmarks:
                self.manager.bookmarks[bid] = bm
        self.manager.save_bookmarks()

    def description(self) -> str:
        return f"Delete {len(self.ids)} bookmark(s)"


class AddBookmarksCommand(Command):
    """Command to add bookmarks"""
    
    def __init__(self, manager, bookmarks: List[Bookmark]):
        self.manager = manager
        self.bookmarks = [bm for bm in (bookmarks or []) if isinstance(bm, Bookmark)]
        self.added_ids: List[int] = []
    
    def execute(self):
        self.added_ids = []
        for bm in self.bookmarks:
            added = self.manager.add_bookmark(bm, save=False)
            self.added_ids.append(added.id)
        self.manager.save_bookmarks()
    
    def undo(self):
        for bid in self.added_ids:
            if bid in self.manager.bookmarks:
                del self.manager.bookmarks[bid]
        self.manager.save_bookmarks()
    
    def description(self) -> str:
        return f"Add {len(self.bookmarks)} bookmark(s)"


class BulkCategorizeCommand(Command):
    """Command for bulk categorization"""
    
    def __init__(self, manager, changes: List[Tuple[int, str, str]]):
        self.manager = manager
        self.changes = []  # (bookmark_id, old_category, new_category)
        for change in changes or []:
            try:
                bid, old_category, new_category = change
                bid = int(bid)
            except (TypeError, ValueError):
                continue
            self.changes.append((
                bid,
                str(old_category or ""),
                str(new_category or "").strip() or "Uncategorized / Needs Review",
            ))
    
    def execute(self):
        for bid, _, new_cat in self.changes:
            bm = self.manager.bookmarks.get(bid)
            if bm:
                bm.category = new_cat
                bm.modified_at = datetime.now().isoformat()
        self.manager.save_bookmarks()
    
    def undo(self):
        for bid, old_cat, _ in self.changes:
            bm = self.manager.bookmarks.get(bid)
            if bm:
                bm.category = old_cat
                bm.modified_at = datetime.now().isoformat()
        self.manager.save_bookmarks()
    
    def description(self) -> str:
        return f"Categorize {len(self.changes)} bookmark(s)"


class TagBookmarksCommand(Command):
    """
        Represents a bookmark tag with metadata.
        
        Attributes:
            name: Tag name (unique identifier)
            color: Hex color code for display
            description: Optional tag description
            created_at: ISO timestamp of creation
            usage_count: Number of bookmarks using this tag
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
        """
    
    def __init__(self, manager, bookmark_ids: List[int], 
                 add_tags: List[str] = None, remove_tags: List[str] = None):
        self.manager = manager
        self.ids = MoveBookmarksCommand._clean_ids(bookmark_ids)
        self.add_tags = self._clean_tags(add_tags)
        self.remove_tags = self._clean_tags(remove_tags)
        self.previous_tags: Dict[int, List[str]] = {}

    @staticmethod
    def _clean_tags(tags) -> List[str]:
        cleaned = []
        seen = set()
        for tag in tags or []:
            text = str(tag or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            cleaned.append(text)
            seen.add(key)
        return cleaned
    
    def execute(self):
        for bid in self.ids:
            bm = self.manager.bookmarks.get(bid)
            if bm:
                self.previous_tags[bid] = bm.tags.copy()
                for tag in self.remove_tags:
                    remove_key = tag.lower()
                    bm.tags = [existing for existing in bm.tags if str(existing).lower() != remove_key]
                for tag in self.add_tags:
                    if not any(str(existing).lower() == tag.lower() for existing in bm.tags):
                        bm.tags.append(tag)
                bm.modified_at = datetime.now().isoformat()
        self.manager.save_bookmarks()
    
    def undo(self):
        for bid, old_tags in self.previous_tags.items():
            bm = self.manager.bookmarks.get(bid)
            if bm:
                bm.tags = old_tags
                bm.modified_at = datetime.now().isoformat()
        self.manager.save_bookmarks()
    
    def description(self) -> str:
        return f"Update tags on {len(self.ids)} bookmark(s)"
