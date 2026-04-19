"""Mixins used by the Tk application coordinator."""

from .ai_actions import AiActionsMixin
from .app_shell import AppShellMixin
from .bookmark_crud import BookmarkCrudMixin
from .bookmarks import BookmarkViewMixin
from .categories import CategoryActionsMixin
from .command_palette import CommandPaletteActionsMixin
from .dashboard import DashboardActionsMixin
from .filters import FilterActionsMixin
from .import_export import ImportExportMixin
from .lifecycle import LifecycleActionsMixin
from .selection import SelectionActionsMixin
from .themes import ThemeActionsMixin
from .tools import ToolsActionsMixin
from .zoom import ZoomActionsMixin

__all__ = [
    "AiActionsMixin",
    "AppShellMixin",
    "BookmarkViewMixin",
    "BookmarkCrudMixin",
    "CategoryActionsMixin",
    "CommandPaletteActionsMixin",
    "DashboardActionsMixin",
    "FilterActionsMixin",
    "ImportExportMixin",
    "LifecycleActionsMixin",
    "SelectionActionsMixin",
    "ThemeActionsMixin",
    "ToolsActionsMixin",
    "ZoomActionsMixin",
]
