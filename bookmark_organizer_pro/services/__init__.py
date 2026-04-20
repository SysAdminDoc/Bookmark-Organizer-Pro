"""Service-layer helpers extracted from the desktop application shell."""

from .ai_tools import (
    AIBatchProcessor,
    AICostTracker,
    AITagSuggester,
    SemanticDuplicateDetector,
)
from .api import BookmarkAPI
from .citation_summarizer import (
    Citation,
    CitationSummarizer,
    CitedSummary,
)
from .dead_link_scanner import (
    DeadLinkRecord,
    DeadLinkScanner,
    ScanProgress,
)
from .digest import DailyDigest, DailyDigestService, DigestSection
from .dup_hybrid import (
    DuplicateGroup,
    DuplicateReport,
    HybridDuplicateDetector,
)
from .embeddings import EmbeddingService
from .encryption import CryptoUnavailable, EncryptedStore
from .favicons import FaviconWrapperGenerator, HighSpeedFaviconManager
from .flows import Flow, FlowManager, FlowStep
from .hybrid_search import HybridResult, HybridSearch
from .icons import AIIconSuggester, IconLibrary
from .ingest import ContentIngestor, IngestResult
from .local_state import BackupScheduler, CategoryColorManager, FontManager, VersionHistory
from .nl_query import NLQueryTranslator, StructuredQuery, execute_query
from .organization import (
    Collection,
    CollectionManager,
    FrequentlyUsedManager,
    SettingsProfile,
    SettingsProfileManager,
    SmartTagManager,
    SmartTagRule,
)
from .rag_chat import ChatMessage, ChatTurn, CollectionChat
from .read_later import ReadLaterQueue
from .rss_feeds import (
    AI_MODES as RSS_AI_MODES,
    FeedConfig,
    FeedIngestor,
    FeedItem,
    FeedRegistry,
    parse_feed,
)
from .snapshot import SnapshotArchiver
from .tag_linter import LintReport, TagLinter, TagSuggestion
from .vector_store import VectorStore, reciprocal_rank_fusion
from .web_tools import (
    AISummarizer,
    LocalArchiver,
    PDFExporter,
    ScreenshotCapture,
    WaybackMachine,
)
from .zip_export import ZipExporter

__all__ = [
    # Existing
    "AIBatchProcessor", "AICostTracker", "AITagSuggester",
    "SemanticDuplicateDetector", "BookmarkAPI",
    "FaviconWrapperGenerator", "HighSpeedFaviconManager",
    "AIIconSuggester", "IconLibrary",
    "BackupScheduler", "CategoryColorManager", "FontManager", "VersionHistory",
    "Collection", "CollectionManager", "FrequentlyUsedManager",
    "SettingsProfile", "SettingsProfileManager",
    "SmartTagManager", "SmartTagRule",
    "AISummarizer", "LocalArchiver", "PDFExporter",
    "ScreenshotCapture", "WaybackMachine",
    # v6.0.0 additions
    "Citation", "CitationSummarizer", "CitedSummary",
    "DeadLinkRecord", "DeadLinkScanner", "ScanProgress",
    "DailyDigest", "DailyDigestService", "DigestSection",
    "DuplicateGroup", "DuplicateReport", "HybridDuplicateDetector",
    "EmbeddingService",
    "CryptoUnavailable", "EncryptedStore",
    "Flow", "FlowManager", "FlowStep",
    "HybridResult", "HybridSearch",
    "ContentIngestor", "IngestResult",
    "NLQueryTranslator", "StructuredQuery", "execute_query",
    "ChatMessage", "ChatTurn", "CollectionChat",
    "ReadLaterQueue",
    "RSS_AI_MODES", "FeedConfig", "FeedIngestor", "FeedItem",
    "FeedRegistry", "parse_feed",
    "SnapshotArchiver",
    "LintReport", "TagLinter", "TagSuggestion",
    "VectorStore", "reciprocal_rank_fusion",
    "ZipExporter",
]
