"""Theme data models and persistence for the application UI.

This module deliberately stays independent of Tk widgets. The main application
owns widget repainting; this layer owns theme serialization, custom-theme file
management, and change notification.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Union

from bookmark_organizer_pro.constants import SETTINGS_FILE, THEMES_DIR
from bookmark_organizer_pro.logging_config import log


_THEME_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")
_HEX_COLOR_PATTERN = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")


@dataclass
class ThemeColors:
    """Complete color palette used by the Tk UI."""

    # Backgrounds
    bg_dark: str = "#f8faf9"
    bg_primary: str = "#f3f6f4"
    bg_secondary: str = "#ffffff"
    bg_tertiary: str = "#e9efec"
    bg_hover: str = "#def7ee"
    bg_card: str = "#ffffff"

    # Text
    text_primary: str = "#121816"
    text_secondary: str = "#52615c"
    text_muted: str = "#858f8b"
    text_link: str = "#0f766e"

    # Accents
    accent_primary: str = "#14b8a6"
    accent_success: str = "#168a5c"
    accent_warning: str = "#b7791f"
    accent_error: str = "#d64545"
    accent_purple: str = "#7c3aed"
    accent_cyan: str = "#0891b2"
    accent_pink: str = "#c026d3"
    accent_orange: str = "#c2410c"

    # UI Elements
    border: str = "#d8e1dd"
    border_muted: str = "#e5ece9"
    border_active: str = "#14b8a6"
    selection: str = "#d7f7ee"
    selected: str = "#0f766e"
    hover: str = "#def7ee"

    # Drag & Drop
    drag_target: str = "#14b8a6"
    drag_target_bg: str = "#d7f7ee"
    drop_zone: str = "#eefbf7"
    drop_zone_active: str = "#d7f7ee"
    drop_zone_border: str = "#14b8a6"

    # Status
    status_success: str = "#168a5c"
    status_warning: str = "#b7791f"
    status_error: str = "#d64545"
    status_info: str = "#0f766e"

    # Scrollbar
    scrollbar_bg: str = "#edf2ef"
    scrollbar_thumb: str = "#cbd8d2"
    scrollbar_thumb_hover: str = "#96aaa1"

    # Cards & Grid
    card_bg: str = "#ffffff"
    card_border: str = "#d8e1dd"
    card_hover: str = "#f4faf7"

    # Special
    ai_accent: str = "#7c3aed"
    tag_bg: str = "#d7f7ee"
    tag_text: str = "#0f766e"

    def to_dict(self) -> Dict[str, str]:
        """Serialize public palette fields."""
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "ThemeColors":
        """Create a palette from partial or forward-compatible data."""
        if not isinstance(data, MappingABC):
            return cls()

        fields = cls.__dataclass_fields__
        defaults = cls()
        values = {
            key: _sanitize_color_value(value, getattr(defaults, key))
            for key, value in data.items()
            if key in fields and value is not None
        }
        return cls(**values)


@dataclass
class ThemeInfo:
    """Theme metadata plus its color palette."""

    name: str
    display_name: str
    author: str = "Built-in"
    version: str = "1.0"
    description: str = ""
    is_dark: bool = True
    colors: ThemeColors = field(default_factory=ThemeColors)

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "author": self.author,
            "version": self.version,
            "description": self.description,
            "is_dark": self.is_dark,
            "colors": self.colors.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "ThemeInfo":
        if not isinstance(data, MappingABC):
            data = {}

        colors = ThemeColors.from_dict(data.get("colors", {}))
        return cls(
            name=_sanitize_theme_name(data.get("name", "custom")),
            display_name=str(data.get("display_name") or "Custom Theme"),
            author=str(data.get("author") or "User"),
            version=str(data.get("version") or "1.0"),
            description=str(data.get("description") or ""),
            is_dark=_coerce_bool(data.get("is_dark", True), default=True),
            colors=colors,
        )


class ThemeManager:
    """Manage current, built-in, and user-created themes."""

    def __init__(
        self,
        built_in_themes: Mapping[str, ThemeInfo],
        settings_file: Path = SETTINGS_FILE,
        themes_dir: Path = THEMES_DIR,
        default_theme: str = "github_dark",
    ):
        if not built_in_themes:
            raise ValueError("ThemeManager requires at least one built-in theme")

        self.built_in_themes = dict(built_in_themes)
        self.settings_file = Path(settings_file)
        self.themes_dir = Path(themes_dir)
        self.default_theme = (
            default_theme if default_theme in self.built_in_themes else next(iter(self.built_in_themes))
        )
        self.current_theme: ThemeInfo = self.built_in_themes[self.default_theme]
        self.custom_themes: Dict[str, ThemeInfo] = {}
        self._theme_change_callbacks: List[Callable[[ThemeInfo], None]] = []

        self.themes_dir.mkdir(parents=True, exist_ok=True)
        self._load_custom_themes()
        self._load_settings()

    def _load_settings(self) -> None:
        """Load theme preference from settings, falling back safely."""
        settings = _read_json_object(self.settings_file)
        theme_name = settings.get("theme", self.default_theme)
        if isinstance(theme_name, str):
            self.current_theme = self.get_all_themes().get(theme_name, self.current_theme)

    def _load_custom_themes(self) -> None:
        """Load custom themes without allowing them to shadow built-ins."""
        for theme_file in self.themes_dir.glob("*.json"):
            try:
                data = _read_json_object(theme_file)
                if not data:
                    continue
                theme = ThemeInfo.from_dict(data)
                theme.name = self._unique_theme_name(theme.name)
                self.custom_themes[theme.name] = theme
            except Exception as exc:
                log.warning(f"Error loading theme {theme_file}: {exc}")

    def save_settings(self) -> None:
        """Persist the active theme while preserving unrelated settings."""
        settings = _read_json_object(self.settings_file)
        settings["theme"] = self.current_theme.name
        _atomic_json_write(self.settings_file, settings)

    def get_all_themes(self) -> Dict[str, ThemeInfo]:
        """Return built-in and custom themes in display order."""
        return {**self.built_in_themes, **self.custom_themes}

    def set_theme(self, theme_name: str) -> bool:
        """Switch to a different theme and notify subscribers."""
        theme = self.get_all_themes().get(str(theme_name or ""))
        if not theme:
            return False

        self.current_theme = theme
        self.save_settings()
        self._notify_theme_change()
        return True

    def create_custom_theme(
        self,
        name: str,
        display_name: str,
        base_theme: str = "github_dark",
        color_overrides: Optional[Mapping[str, object]] = None,
    ) -> ThemeInfo:
        """Create and persist a custom theme based on an existing theme."""
        base = self.built_in_themes.get(base_theme, self.built_in_themes[self.default_theme])
        safe_name = self._unique_theme_name(_sanitize_theme_name(name))

        new_colors_dict = base.colors.to_dict()
        if color_overrides:
            allowed = ThemeColors.__dataclass_fields__
            new_colors_dict.update(
                {
                    key: str(value)
                    for key, value in color_overrides.items()
                    if key in allowed and value is not None
                }
            )

        new_theme = ThemeInfo(
            name=safe_name,
            display_name=str(display_name or safe_name),
            author="User",
            version="1.0",
            description="Custom theme",
            is_dark=base.is_dark,
            colors=ThemeColors.from_dict(new_colors_dict),
        )

        self._write_custom_theme(new_theme)
        self.custom_themes[new_theme.name] = new_theme
        return new_theme

    def delete_custom_theme(self, name: str) -> bool:
        """Delete a custom theme. Built-ins cannot be deleted."""
        safe_name = _sanitize_theme_name(name)
        if safe_name not in self.custom_themes:
            return False

        theme_file = self.themes_dir / f"{safe_name}.json"
        try:
            if theme_file.exists():
                theme_file.unlink()
        except OSError as exc:
            log.warning(f"Could not delete theme file {theme_file}: {exc}")

        del self.custom_themes[safe_name]
        if self.current_theme.name == safe_name:
            self.current_theme = self.built_in_themes[self.default_theme]
            self.save_settings()
            self._notify_theme_change()
        return True

    def export_theme(self, theme_name: str, filepath: Union[str, Path]) -> bool:
        """Export a theme to a JSON file."""
        theme = self.get_all_themes().get(str(theme_name or ""))
        if not theme or not filepath:
            return False

        _atomic_json_write(Path(filepath), theme.to_dict())
        return True

    def import_theme(self, filepath: Union[str, Path]) -> Optional[ThemeInfo]:
        """Import a theme file and store it as a custom theme."""
        try:
            data = _read_json_object(Path(filepath))
            if not data:
                return None

            theme = ThemeInfo.from_dict(data)
            theme.name = self._unique_theme_name(theme.name)
            self._write_custom_theme(theme)
            self.custom_themes[theme.name] = theme
            return theme
        except Exception as exc:
            log.error(f"Error importing theme: {exc}")
            return None

    def add_theme_change_callback(self, callback: Callable[[ThemeInfo], None]) -> None:
        """Register a callback for theme changes."""
        if callable(callback) and callback not in self._theme_change_callbacks:
            self._theme_change_callbacks.append(callback)

    def remove_theme_change_callback(self, callback: Callable[[ThemeInfo], None]) -> None:
        """Remove a theme change callback."""
        if callback in self._theme_change_callbacks:
            self._theme_change_callbacks.remove(callback)

    def _notify_theme_change(self) -> None:
        """Notify subscribers without coupling to any specific widget toolkit."""
        for callback in list(self._theme_change_callbacks):
            try:
                callback(self.current_theme)
            except Exception as exc:
                log.error(f"Error in theme callback: {exc}")

    def _unique_theme_name(self, name: str) -> str:
        base_name = _sanitize_theme_name(name)
        candidate = base_name
        counter = 1
        while candidate in self.built_in_themes or candidate in self.custom_themes:
            candidate = f"{base_name}_{counter}"
            counter += 1
        return candidate

    def _write_custom_theme(self, theme: ThemeInfo) -> None:
        theme.name = _sanitize_theme_name(theme.name)
        _atomic_json_write(self.themes_dir / f"{theme.name}.json", theme.to_dict())

    @property
    def colors(self) -> ThemeColors:
        """Return the active palette."""
        return self.current_theme.colors


def _sanitize_theme_name(value: object, fallback: str = "custom") -> str:
    text = str(value or "").strip()
    text = _THEME_NAME_PATTERN.sub("_", text).strip("._-")
    return (text or fallback)[:80]


def _sanitize_color_value(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text if _HEX_COLOR_PATTERN.match(text) else fallback


def _coerce_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _read_json_object(filepath: Path) -> Dict[str, object]:
    try:
        with Path(filepath).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        log.warning(f"Could not read JSON file {filepath}: {exc}")
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
