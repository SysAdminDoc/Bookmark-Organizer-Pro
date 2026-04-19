"""Backend manager classes extracted from the desktop application shell."""

from .bookmarks import BookmarkManager
from .tags import TagManager

__all__ = ["BookmarkManager", "TagManager"]
