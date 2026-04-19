"""AI bookmark processing actions for the app coordinator."""

from __future__ import annotations

from .ai_categorization import AiCategorizationMixin
from .ai_enrichment import AiEnrichmentMixin
from .ai_titles import AiTitleImprovementMixin


class AiProcessingMixin(AiCategorizationMixin, AiEnrichmentMixin, AiTitleImprovementMixin):
    """AI categorization, tag suggestion, summaries, and title improvement workflows."""
