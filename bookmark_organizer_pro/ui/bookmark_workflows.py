"""Compatibility exports for bookmark workflow panels and dialogs.

The legacy module used to contain every bookmark workflow widget. The concrete
implementations now live in focused modules while this facade preserves existing
imports from ``bookmark_organizer_pro.ui.bookmark_workflows``.
"""

from __future__ import annotations

from .workflow_runtime import _open_external_url
from .workflow_smart_filters import SmartFiltersPanel
from .workflow_reports import ReportGenerator
from .workflow_quick_add import QuickAddDialog
from .workflow_bulk_tags import BulkTagEditorDialog
from .workflow_detail_panel import BookmarkDetailPanel
from .workflow_selective_export import SelectiveExportDialog
from .workflow_emoji_picker import EmojiPicker

__all__ = [
    "BookmarkDetailPanel",
    "BulkTagEditorDialog",
    "EmojiPicker",
    "QuickAddDialog",
    "ReportGenerator",
    "SelectiveExportDialog",
    "SmartFiltersPanel",
    "_open_external_url",
]
