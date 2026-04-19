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
    size_title: int = 16
    size_header: int = 12
    size_body: int = 10
    size_small: int = 9
    size_tiny: int = 8

    def title(self, bold: bool = True) -> Tuple[str, int, str]:
        return (self.family, self.size_title, "bold" if bold else "normal")

    def header(self, bold: bool = True) -> Tuple[str, int, str]:
        return (self.family, self.size_header, "bold" if bold else "normal")

    def body(self, bold: bool = False) -> Tuple[str, int, str]:
        return (self.family, self.size_body, "bold" if bold else "normal")

    def small(self, bold: bool = False) -> Tuple[str, int, str]:
        return (self.family, self.size_small, "bold" if bold else "normal")

    def tiny(self, bold: bool = False) -> Tuple[str, int, str]:
        return (self.family, self.size_tiny, "bold" if bold else "normal")

    def custom(self, size: int, bold: bool = False) -> Tuple[str, int, str]:
        return (self.family, size, "bold" if bold else "normal")


def get_system_font() -> str:
    """Get the best available system font for the platform."""
    if IS_WINDOWS:
        return "Segoe UI"
    if IS_MAC:
        return "SF Pro Display"
    return "DejaVu Sans"


FONTS = FontConfig(family=get_system_font())


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

    BUTTON_HEIGHT = 34
    INPUT_HEIGHT = 36
    ROW_HEIGHT = 32
    TREEVIEW_ROW_HEIGHT = 42
    HEADER_HEIGHT = 88
    SUMMARY_STRIP_HEIGHT = 112
    STATUS_BAR_HEIGHT = 34
    TOUCH_TARGET_MIN = 36
    FOCUS_RING_WIDTH = 2

    ICON_SM = 16
    ICON_MD = 20
    ICON_LG = 24

    SIDEBAR_WIDTH = 276
    SIDEBAR_MIN_WIDTH = 260
    RIGHT_SIDEBAR_WIDTH = 310
    CONTENT_PAD_X = 20
    CONTENT_PAD_Y = 18
    PANEL_PAD = 16
    TOOLBAR_GAP = 6

    ANIMATION_FAST = 100
    ANIMATION_NORMAL = 200
    ANIMATION_SLOW = 300


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
    """Pick dark or light foreground text for a solid background color."""
    try:
        color = str(hex_color or "").lstrip("#")
        if len(color) == 3:
            color = "".join(ch * 2 for ch in color)
        r, g, b = (int(color[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception:
        return "#ffffff"

    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    luminance = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
    return "#07100f" if luminance > 0.42 else "#ffffff"
