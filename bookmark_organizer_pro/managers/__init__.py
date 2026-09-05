"""Backend manager classes extracted from the desktop application shell."""

from .bookmarks import BookmarkAddResult, BookmarkManager, TrashPurgeResult
from .tags import TagManager

__all__ = ["BookmarkAddResult", "BookmarkManager", "TagManager", "TrashPurgeResult"]
