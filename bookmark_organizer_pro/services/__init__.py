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
from .feed_export import export_opds, render_opds
from .flows import Flow, FlowManager, FlowStep
from .bookmark_graph import (
    BookmarkGraph,
    GraphEdge,
    GraphNode,
    apply_force_layout,
    build_bookmark_graph,
    export_bookmark_graph_json,
)
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
from .rag_chat import (
    ChatMessage,
    ChatStreamEvent,
    ChatStreamResult,
    ChatTurn,
    CollectionChat,
    build_chat_stream_events,
    normalize_stream_chunk_chars,
    split_answer_chunks,
)
from .read_later import ReadLaterQueue
from .reader_annotations import (
    HIGHLIGHT_COLORS,
    ReaderAnnotationStore,
    ReaderHighlight,
    export_bookmark_highlights,
    normalize_highlight_color,
    read_extracted_text,
    render_highlights_markdown,
)
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
from .updates import (
    StagedUpdateStatus,
    UpdateApplyPreflightResult,
    UpdateCheckResult,
    UpdateCleanupResult,
    UpdateDownloadResult,
    UpdateManager,
    UpdatePolicy,
    UpdateStatus,
)
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
    "export_opds", "render_opds",
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
    "BookmarkGraph", "GraphEdge", "GraphNode",
    "apply_force_layout", "build_bookmark_graph", "export_bookmark_graph_json",
    "HybridResult", "HybridSearch",
    "ContentIngestor", "IngestResult",
    "NLQueryTranslator", "StructuredQuery", "execute_query",
    "ChatMessage", "ChatStreamEvent", "ChatStreamResult", "ChatTurn", "CollectionChat",
    "build_chat_stream_events", "normalize_stream_chunk_chars", "split_answer_chunks",
    "ReadLaterQueue",
    "HIGHLIGHT_COLORS", "ReaderAnnotationStore", "ReaderHighlight",
    "export_bookmark_highlights", "normalize_highlight_color",
    "read_extracted_text", "render_highlights_markdown",
    "RSS_AI_MODES", "FeedConfig", "FeedIngestor", "FeedItem",
    "FeedRegistry", "parse_feed",
    "SnapshotArchiver",
    "LintReport", "TagLinter", "TagSuggestion",
    "StagedUpdateStatus", "UpdateApplyPreflightResult",
    "UpdateCheckResult", "UpdateCleanupResult", "UpdateDownloadResult",
    "UpdateManager", "UpdatePolicy", "UpdateStatus",
    "VectorStore", "reciprocal_rank_fusion",
    "ZipExporter",
]
