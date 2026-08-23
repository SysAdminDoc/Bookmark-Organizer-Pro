"""Service-layer helpers extracted from the desktop application shell."""

from .ai_tools import (
    AIBatchProcessor,
    AICostTracker,
    AITagSuggester,
    SemanticDuplicateDetector,
)
from .auto_snapshot import SnapshotScheduler
from .ai_operation import (
    AIBudget,
    AIBudgetExceeded,
    AICancellationToken,
    AIOperation,
    AIOperationCancelled,
    AIOperationError,
    call_ai,
    estimate_tokens,
    operation_scope,
)
from .api import BookmarkAPI
from .ai_context import (
    CitedOutput,
    UntrustedEvidenceBundle,
    UntrustedEvidenceChunk,
    build_untrusted_evidence,
    enforce_citation_policy,
)
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
from .favicons import (
    FaviconPrivacyPolicy,
    FaviconWrapperGenerator,
    HighSpeedFaviconManager,
    load_favicon_policy,
    save_favicon_policy,
)
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
from .job_ledger import JobLedger, JobRecord, JobRun
from .youtube_transcript import (
    TranscriptResult,
    YouTubeTranscriptService,
    classify_transcript_error,
    fetch_transcript,
    is_youtube_url,
    normalize_language,
    normalize_timeout,
    save_transcript,
)
from .extraction_templates import (
    STRUCTURED_METADATA_KEY,
    ExtractionField,
    ExtractionTemplate,
    StructuredExtractionResult,
    extract_structured_metadata,
    format_structured_value,
    load_extraction_templates,
    structured_metadata_fields,
    structured_metadata_payload,
)
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
from .organization_rules import (
    OrganizationPreview,
    OrganizationRule,
    OrganizationRuleChange,
    OrganizationRuleConflict,
    OrganizationRules,
    OrganizationRulesService,
    OrganizationRunReport,
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
from .reader_progress import (
    DEFAULT_PROGRESS_STATE,
    PROGRESS_STATES,
    ReaderProgress,
    ReaderProgressStore,
    ReaderProgressWrite,
    source_text_sha256 as reader_progress_source_sha256,
)
from .processing_timeline import (
    ProcessingTimeline,
    ProcessingTimelineEvent,
    ProcessingTimelineService,
    sanitize_processing_error,
)
from .highlight_workspace import (
    GlobalHighlightsService,
    HighlightWorkspace,
    HighlightWorkspacePage,
    HighlightWorkspaceQuery,
    HighlightWorkspaceRecord,
    HighlightWorkspaceService,
)
from .recovery_bundle import (
    BundleReport,
    RestoreResult,
    create_recovery_bundle,
    restore_recovery_bundle,
    validate_recovery_bundle,
    verify_recovery_bundle_coverage,
)
from .rss_feeds import (
    AI_MODES as RSS_AI_MODES,
    FeedConfig,
    FeedIngestor,
    FeedItem,
    FeedRegistry,
    parse_feed,
)
from .snapshot import (
    SnapshotArchiver,
    SnapshotBackendAttempt,
    SnapshotFailureRecord,
    SnapshotFailureStore,
    SnapshotFormat,
    SnapshotManifest,
    classify_snapshot_payload,
    ensure_snapshot_manifest,
    load_snapshot_manifest,
    open_snapshot_file,
)
from .settings_store import (
    SettingsConflictError,
    SettingsSnapshot,
    SettingsStore,
    load_settings,
    update_settings,
)
from .tag_linter import LintReport, TagLinter, TagSuggestion
from .updates import (
    StagedUpdateStatus,
    UpdateApplyPreflightResult,
    UpdateApplyPlan,
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
    "SnapshotScheduler",
    "AIBudget", "AIBudgetExceeded", "AICancellationToken",
    "AIOperation", "AIOperationCancelled", "AIOperationError",
    "call_ai", "estimate_tokens", "operation_scope",
    "CitedOutput", "UntrustedEvidenceBundle", "UntrustedEvidenceChunk",
    "build_untrusted_evidence", "enforce_citation_policy",
    "FaviconPrivacyPolicy", "FaviconWrapperGenerator", "HighSpeedFaviconManager",
    "load_favicon_policy", "save_favicon_policy",
    "export_opds", "render_opds",
    "AIIconSuggester", "IconLibrary",
    "BackupScheduler", "CategoryColorManager", "FontManager", "VersionHistory",
    "Collection", "CollectionManager", "FrequentlyUsedManager",
    "SettingsProfile", "SettingsProfileManager",
    "SmartTagManager", "SmartTagRule",
    "OrganizationPreview", "OrganizationRule", "OrganizationRuleChange",
    "OrganizationRuleConflict", "OrganizationRules", "OrganizationRulesService",
    "OrganizationRunReport",
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
    "JobLedger", "JobRecord", "JobRun",
    "STRUCTURED_METADATA_KEY", "ExtractionField", "ExtractionTemplate",
    "StructuredExtractionResult", "extract_structured_metadata",
    "format_structured_value", "load_extraction_templates",
    "structured_metadata_fields", "structured_metadata_payload",
    "NLQueryTranslator", "StructuredQuery", "execute_query",
    "ChatMessage", "ChatStreamEvent", "ChatStreamResult", "ChatTurn", "CollectionChat",
    "build_chat_stream_events", "normalize_stream_chunk_chars", "split_answer_chunks",
    "ReadLaterQueue",
    "HIGHLIGHT_COLORS", "ReaderAnnotationStore", "ReaderHighlight",
    "export_bookmark_highlights", "normalize_highlight_color",
    "read_extracted_text", "render_highlights_markdown",
    "DEFAULT_PROGRESS_STATE", "PROGRESS_STATES", "ReaderProgress",
    "ReaderProgressStore", "ReaderProgressWrite", "reader_progress_source_sha256",
    "ProcessingTimeline", "ProcessingTimelineEvent", "ProcessingTimelineService",
    "sanitize_processing_error",
    "GlobalHighlightsService", "HighlightWorkspace", "HighlightWorkspacePage",
    "HighlightWorkspaceQuery", "HighlightWorkspaceRecord", "HighlightWorkspaceService",
    "TranscriptResult", "YouTubeTranscriptService", "classify_transcript_error",
    "fetch_transcript", "is_youtube_url", "normalize_language",
    "normalize_timeout", "save_transcript",
    "BundleReport", "RestoreResult", "create_recovery_bundle",
    "restore_recovery_bundle", "validate_recovery_bundle",
    "verify_recovery_bundle_coverage",
    "RSS_AI_MODES", "FeedConfig", "FeedIngestor", "FeedItem",
    "FeedRegistry", "parse_feed",
    "SnapshotArchiver", "SnapshotBackendAttempt", "SnapshotFailureRecord",
    "SnapshotFailureStore", "SnapshotFormat", "SnapshotManifest",
    "classify_snapshot_payload", "ensure_snapshot_manifest",
    "load_snapshot_manifest", "open_snapshot_file",
    "SettingsConflictError", "SettingsSnapshot", "SettingsStore",
    "load_settings", "update_settings",
    "LintReport", "TagLinter", "TagSuggestion",
    "StagedUpdateStatus", "UpdateApplyPreflightResult", "UpdateApplyPlan",
    "UpdateCheckResult", "UpdateCleanupResult", "UpdateDownloadResult",
    "UpdateManager", "UpdatePolicy", "UpdateStatus",
    "VectorStore", "reciprocal_rank_fusion",
    "ZipExporter",
]
