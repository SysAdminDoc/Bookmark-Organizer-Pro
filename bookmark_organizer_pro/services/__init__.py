"""Service-layer helpers extracted from the desktop application shell."""

from .ai_tools import (
    AIBatchProcessor,
    AICostTracker,
    AITagSuggester,
    SemanticDuplicateDetector,
)
from .api import BookmarkAPI
from .favicons import FaviconWrapperGenerator, HighSpeedFaviconManager
from .icons import AIIconSuggester, IconLibrary
from .local_state import BackupScheduler, CategoryColorManager, FontManager, VersionHistory
from .organization import (
    Collection,
    CollectionManager,
    FrequentlyUsedManager,
    SettingsProfile,
    SettingsProfileManager,
    SmartTagManager,
    SmartTagRule,
)
from .web_tools import (
    AISummarizer,
    LocalArchiver,
    PDFExporter,
    ScreenshotCapture,
    WaybackMachine,
)

__all__ = [
    "AIBatchProcessor",
    "AICostTracker",
    "AITagSuggester",
    "SemanticDuplicateDetector",
    "BookmarkAPI",
    "FaviconWrapperGenerator",
    "HighSpeedFaviconManager",
    "AIIconSuggester",
    "IconLibrary",
    "BackupScheduler",
    "CategoryColorManager",
    "FontManager",
    "VersionHistory",
    "Collection",
    "CollectionManager",
    "FrequentlyUsedManager",
    "SettingsProfile",
    "SettingsProfileManager",
    "SmartTagManager",
    "SmartTagRule",
    "AISummarizer",
    "LocalArchiver",
    "PDFExporter",
    "ScreenshotCapture",
    "WaybackMachine",
]
