"""Shared AI action helpers for the app coordinator."""

from __future__ import annotations

import re
from tkinter import messagebox
from typing import List, Optional

from bookmark_organizer_pro.i18n import _, format_message

try:
    import requests
except ImportError:  # pragma: no cover - optional runtime dependency
    requests = None

from bookmark_organizer_pro.ai import AI_PROVIDERS, create_ai_client
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark


class AiSupportMixin:
    """AI client, selection, readiness, error, and response parsing helpers."""

    def _get_ai_client(self):
        """Get configured AI client"""
        if not self.ai_config.is_configured():
            return None
        
        try:
            return create_ai_client(self.ai_config)
        except Exception:
            log.warning("Error creating AI client", exc_info=True)
            return None

    def _ai_provider_name(self) -> str:
        """Return the configured AI provider display name."""
        provider = self.ai_config.get_provider()
        info = AI_PROVIDERS.get(provider)
        return info.display_name if info else provider.title()

    def _ensure_ai_ready(self, action_name: str) -> bool:
        """Open Assistant Settings when a feature requires a configured provider."""
        if self.ai_config.is_configured():
            return True

        self._set_status(f"{action_name} needs Assistant Settings before it can run")
        if hasattr(self, "_show_toast"):
            self._show_toast("Choose an assistant provider to continue", "info")
        self._show_ai_settings()
        return False

    def _get_selected_bookmarks_for_action(self, title: str, message: str) -> List[Bookmark]:
        """Return selected bookmarks or show a helpful empty-selection message."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(title, message, parent=self.root)
            self._set_status("Select one or more bookmarks to continue")
            return []

        bookmarks = []
        for item_id in selected:
            bm = self.bookmark_manager.get_bookmark(int(item_id))
            if bm:
                bookmarks.append(bm)

        if not bookmarks:
            messagebox.showinfo(
                _("Selection Not Available"),
                _("The selected rows are no longer available. Refresh the list and try again."),
                parent=self.root
            )
            self._set_status("Selection could not be used")
        return bookmarks

    def _show_ai_client_error(self, action_name: str):
        """Show a consistent AI connection/configuration failure message."""
        messagebox.showerror(
            _("AI Connection Unavailable"),
            format_message('{value_0} could not start because the configured AI client could not be created.\n\nOpen Assistant Settings to confirm the provider, model, and credential.', value_0=action_name),
            parent=self.root
        )
        self._set_status("Assistant settings need attention")

    def _extract_json_object_text(self, text: str) -> Optional[str]:
        """Extract a JSON object from a provider response."""
        if "```json" in text:
            match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
            if match:
                text = match.group(1)
        elif "```" in text:
            match = re.search(r"```\s*([\s\S]*?)\s*```", text)
            if match:
                text = match.group(1)

        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            return text[start:end + 1]
        return None
