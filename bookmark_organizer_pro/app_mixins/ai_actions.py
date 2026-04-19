"""Composite AI actions mixin for the app coordinator."""

from __future__ import annotations

from .ai_menu_data import AiMenuDataMixin
from .ai_processing import AiProcessingMixin
from .ai_settings import AiSettingsMixin
from .ai_support import AiSupportMixin


class AiActionsMixin(AiMenuDataMixin, AiProcessingMixin, AiSettingsMixin, AiSupportMixin):
    """AI menu, processing, import/export, and settings actions."""

