"""Report generator adapter used by the desktop application."""

from __future__ import annotations

from bookmark_organizer_pro.constants import APP_NAME, APP_VERSION
from bookmark_organizer_pro.managers import BookmarkManager

from .reports import ReportGenerator as BaseReportGenerator
from .widget_runtime import get_theme

# =============================================================================
# Export Reports (PDF/HTML Analytics)
# =============================================================================
class ReportGenerator(BaseReportGenerator):
    """Main-app adapter for themed analytics reports."""

    def __init__(self, bookmark_manager: BookmarkManager):
        super().__init__(
            bookmark_manager,
            theme_provider=get_theme,
            app_name=APP_NAME,
            app_version=f"v{APP_VERSION}",
        )
