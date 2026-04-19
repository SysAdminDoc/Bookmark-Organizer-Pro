"""Runtime helpers for bookmark workflow dialogs."""

from __future__ import annotations

import webbrowser

from bookmark_organizer_pro.utils.runtime import open_external_url


def _open_external_url(url: str) -> bool:
    """Open external URLs through the shared runtime helper."""
    return open_external_url(url, opener=webbrowser.open)
