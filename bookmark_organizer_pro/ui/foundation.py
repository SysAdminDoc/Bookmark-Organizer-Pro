"""Design-system primitives and display helpers.

These helpers are deliberately independent of Tkinter widgets. UI classes can
import them, tests can exercise them quickly, and future Qt/web frontends can
reuse the same product formatting rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from bookmark_organizer_pro.constants import IS_MAC, IS_WINDOWS


@dataclass
class FontConfig:
    """Centralized font configuration for consistent typography."""

    family: str
    mono_family: str = ""
    size_display: int = 28
    size_hero: int = 22
    size_title: int = 18
    size_subtitle: int = 14
    size_header: int = 13
    size_body: int = 11
    size_small: int = 10
    size_tiny: int = 9

    def display(self, bold: bool = True) -> Tuple[str, int, str]:
        return (self.family, self.size_display, "bold" if bold else "normal")

    def hero(self, bold: bool = True) -> Tuple[str, int, str]:
        return (self.family, self.size_hero, "bold" if bold else "normal")

    def title(self, bold: bool = True) -> Tuple[str, int, str]:
        return (self.family, self.size_title, "bold" if bold else "normal")

    def subtitle(self, bold: bool = True) -> Tuple[str, int, str]:
        return (self.family, self.size_subtitle, "bold" if bold else "normal")

    def header(self, bold: bool = True) -> Tuple[str, int, str]:
        return (self.family, self.size_header, "bold" if bold else "normal")

    def body(self, bold: bool = False) -> Tuple[str, int, str]:
        return (self.family, self.size_body, "bold" if bold else "normal")

    def small(self, bold: bool = False) -> Tuple[str, int, str]:
        return (self.family, self.size_small, "bold" if bold else "normal")

    def tiny(self, bold: bool = False) -> Tuple[str, int, str]:
        return (self.family, self.size_tiny, "bold" if bold else "normal")

    def mono(self, size: Optional[int] = None) -> Tuple[str, int, str]:
        return (self.mono_family or "Consolas", size or self.size_small, "normal")

    def custom(self, size: int, bold: bool = False) -> Tuple[str, int, str]:
        return (self.family, size, "bold" if bold else "normal")


def get_system_font() -> str:
    """Get the best available system font for the platform."""
    if IS_WINDOWS:
        return "Segoe UI"
    if IS_MAC:
        return "SF Pro Display"
    return "DejaVu Sans"


def get_mono_font() -> str:
    if IS_WINDOWS:
        return "Cascadia Mono"
    if IS_MAC:
        return "SF Mono"
    return "JetBrains Mono"


FONTS = FontConfig(family=get_system_font(), mono_family=get_mono_font())


class DesignTokens:
    """Centralized spacing, sizing, and motion constants."""

    SPACE_XS = 4
    SPACE_SM = 8
    SPACE_MD = 12
    SPACE_LG = 16
    SPACE_XL = 24
    SPACE_XXL = 32

    RADIUS_SM = 4
    RADIUS_MD = 6
    RADIUS_LG = 8

    BUTTON_HEIGHT = 40
    BUTTON_PAD_X = 14
    BUTTON_PAD_Y = 7
    INPUT_HEIGHT = 36
    ROW_HEIGHT = 32
    TREEVIEW_ROW_HEIGHT = 36
    HEADER_HEIGHT = 70
    SUMMARY_STRIP_HEIGHT = 112
    STATUS_BAR_HEIGHT = 34
    TOUCH_TARGET_MIN = 44
    FOCUS_RING_WIDTH = 2

    ICON_SM = 16
    ICON_MD = 20
    ICON_LG = 24

    SIDEBAR_WIDTH = 256
    SIDEBAR_MIN_WIDTH = 240
    RIGHT_SIDEBAR_WIDTH = 368
    CONTENT_PAD_X = 24
    CONTENT_PAD_Y = 18
    PANEL_PAD = 16
    TOOLBAR_GAP = 6

    LINE_HEIGHT_FACTOR = 1.5

    ANIMATION_FAST = 100
    ANIMATION_NORMAL = 200
    ANIMATION_SLOW = 300

    # Desktop controls stay compact, while primary actions meet the larger
    # target used by the first-run and import flows.
    PRIMARY_TARGET_MIN = 44


def pluralize(count: int, singular: str, plural: Optional[str] = None) -> str:
    """Return a count with a correctly pluralized label for UI copy."""
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def format_compact_count(value: int) -> str:
    """Format count badges without creating noisy wide pills."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return "0"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    if value >= 10_000:
        return f"{value // 1_000}K"
    if value >= 1_000:
        return f"{value / 1_000:.1f}".rstrip("0").rstrip(".") + "K"
    return str(value)


def truncate_middle(text: str, max_length: int = 48) -> str:
    """Keep both ends of long URLs visible in dense rows."""
    text = str(text or "").strip()
    if len(text) <= max_length:
        return text
    if max_length <= 8:
        return text[:max_length]
    head = max(4, (max_length - 1) // 2)
    tail = max(4, max_length - head - 1)
    return f"{text[:head]}…{text[-tail:]}"


def display_or_fallback(value, fallback: str = "—") -> str:
    """Normalize blank user data before it reaches labels and table cells."""
    text = str(value or "").strip()
    return text if text else fallback


def readable_text_on(hex_color: str) -> str:
    """Pick dark or light foreground text for maximum contrast on a background.

    Uses WCAG relative-luminance contrast ratio comparison against both
    candidates and returns whichever gives the higher ratio.
    """
    try:
        color = str(hex_color or "").lstrip("#")
        if len(color) == 3:
            color = "".join(ch * 2 for ch in color)
        r, g, b = (int(color[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception:
        return "#ffffff"

    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    bg_lum = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

    # Contrast ratio against dark (#07100f ~ 0.012) and light (#ffffff = 1.0)
    dark_lum = 0.012
    light_lum = 1.0
    contrast_dark = (max(bg_lum, dark_lum) + 0.05) / (min(bg_lum, dark_lum) + 0.05)
    contrast_light = (max(bg_lum, light_lum) + 0.05) / (min(bg_lum, light_lum) + 0.05)
    return "#07100f" if contrast_dark >= contrast_light else "#ffffff"


def contrast_ratio(first: str, second: str) -> float:
    """Return the WCAG contrast ratio for two hex colors."""
    def luminance(value: str) -> float:
        text = str(value or "").lstrip("#")
        if len(text) == 3:
            text = "".join(character * 2 for character in text)
        if len(text) != 6:
            return 1.0
        try:
            channels = [int(text[index:index + 2], 16) / 255 for index in (0, 2, 4)]
        except ValueError:
            return 1.0
        linear = [
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    first_luminance = luminance(first)
    second_luminance = luminance(second)
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)
