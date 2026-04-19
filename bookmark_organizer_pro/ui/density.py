"""Display-density preferences for the desktop UI."""

from __future__ import annotations

import json
import os
import tempfile
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

from bookmark_organizer_pro.constants import SETTINGS_FILE
from bookmark_organizer_pro.logging_config import log


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
        self.default_density = default_density
        self._density = default_density
        self._callbacks: List[Callable[[DisplayDensity], None]] = []
        self._load_settings()

    def _load_settings(self) -> None:
        data = _read_json_object(self.settings_file)
        self._density = _coerce_density(data.get("display_density"), self.default_density)

    def _save_settings(self) -> None:
        data = _read_json_object(self.settings_file)
        data["display_density"] = self._density.value
        _atomic_json_write(self.settings_file, data)

    @property
    def density(self) -> DisplayDensity:
        return self._density

    @density.setter
    def density(self, value: Union[DisplayDensity, str]) -> None:
        next_density = _coerce_density(value, self.default_density)
        if self._density != next_density:
            self._density = next_density
            self._save_settings()
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


def _read_json_object(filepath: Path) -> Dict[str, object]:
    try:
        with Path(filepath).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        log.warning(f"Could not read settings file {filepath}: {exc}")
        return {}


def _atomic_json_write(filepath: Path, data: Mapping[str, object], indent: int = 2) -> None:
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=filepath.parent, suffix=".tmp", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(data), handle, indent=indent, ensure_ascii=False)
        os.replace(temp_path, filepath)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
