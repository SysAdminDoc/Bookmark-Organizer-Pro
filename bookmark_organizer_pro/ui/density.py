"""Display-density preferences for the desktop UI."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Union

from bookmark_organizer_pro.constants import SETTINGS_FILE
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.services.settings_store import SettingsStore


class DisplayDensity(Enum):
    """Display density options for list rows, cards, and touch targets."""

    COMPACT = "compact"
    COMFORTABLE = "comfortable"
    SPACIOUS = "spacious"


DENSITY_SETTINGS: Dict[DisplayDensity, Dict[str, int]] = {
    DisplayDensity.COMPACT: {
        "row_height": 24,
        "padding_y": 4,
        "font_size": 9,
        "card_padding": 6,
        "icon_size": 14,
    },
    DisplayDensity.COMFORTABLE: {
        "row_height": 32,
        "padding_y": 8,
        "font_size": 10,
        "card_padding": 10,
        "icon_size": 16,
    },
    DisplayDensity.SPACIOUS: {
        "row_height": 44,
        "padding_y": 12,
        "font_size": 11,
        "card_padding": 15,
        "icon_size": 20,
    },
}


class DensityManager:
    """Load, save, and broadcast display-density preference changes."""

    def __init__(
        self,
        settings_file: Path = SETTINGS_FILE,
        default_density: DisplayDensity = DisplayDensity.COMFORTABLE,
    ):
        self.settings_file = Path(settings_file)
        self._settings_store = SettingsStore(self.settings_file)
        self._settings_snapshot = None
        self.default_density = default_density
        self._density = default_density
        self._callbacks: List[Callable[[DisplayDensity], None]] = []
        self._load_settings()

    def _load_settings(self) -> None:
        self._settings_snapshot = self._settings_store.read()
        self._density = _coerce_density(
            self._settings_snapshot.get("display_density"),
            self.default_density,
        )

    def _save_settings(self) -> None:
        self._settings_snapshot = self._settings_store.set(
            "display_density",
            self._density.value,
            base_snapshot=self._settings_snapshot,
        )

    @property
    def density(self) -> DisplayDensity:
        return self._density

    @density.setter
    def density(self, value: Union[DisplayDensity, str]) -> None:
        next_density = _coerce_density(value, self.default_density)
        if self._density != next_density:
            previous_density = self._density
            self._density = next_density
            try:
                self._save_settings()
            except Exception:
                self._density = previous_density
                raise
            self._notify_callbacks()

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Return one density-specific setting."""
        return DENSITY_SETTINGS[self._density].get(key, default)

    def add_callback(self, callback: Callable[[DisplayDensity], None]) -> None:
        """Subscribe to density changes."""
        if callable(callback) and callback not in self._callbacks:
            self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[DisplayDensity], None]) -> None:
        """Unsubscribe from density changes."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify_callbacks(self) -> None:
        for callback in list(self._callbacks):
            try:
                callback(self._density)
            except Exception as exc:
                log.warning(f"Display density callback failed: {exc}")


def _coerce_density(value: object, default: DisplayDensity) -> DisplayDensity:
    if isinstance(value, DisplayDensity):
        return value
    try:
        return DisplayDensity(str(value))
    except Exception:
        return default
