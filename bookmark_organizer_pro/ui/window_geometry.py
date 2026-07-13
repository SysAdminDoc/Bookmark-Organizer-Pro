"""Screen-aware geometry helpers for desktop dialogs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WindowGeometry:
    width: int
    height: int
    x: int
    y: int


def fit_window_geometry(
    desired_width: int,
    desired_height: int,
    screen_width: int,
    screen_height: int,
    *,
    margin: int = 24,
    minimum_width: int = 320,
    minimum_height: int = 280,
) -> WindowGeometry:
    """Return centered dimensions that never exceed the usable viewport."""
    usable_width = max(minimum_width, int(screen_width) - (2 * margin))
    usable_height = max(minimum_height, int(screen_height) - (2 * margin))
    width = min(max(minimum_width, int(desired_width)), usable_width)
    height = min(max(minimum_height, int(desired_height)), usable_height)
    return WindowGeometry(
        width=width,
        height=height,
        x=max(margin, (int(screen_width) - width) // 2),
        y=max(margin, (int(screen_height) - height) // 2),
    )


def apply_screen_aware_geometry(
    window,
    desired_width: int,
    desired_height: int,
    *,
    margin: int = 24,
    screen_width: int | None = None,
    screen_height: int | None = None,
) -> WindowGeometry:
    """Fit and apply dialog geometry, with optional deterministic smoke dimensions."""
    geometry = fit_window_geometry(
        desired_width,
        desired_height,
        screen_width if screen_width is not None else window.winfo_screenwidth(),
        screen_height if screen_height is not None else window.winfo_screenheight(),
        margin=margin,
    )
    window.geometry(
        f"{geometry.width}x{geometry.height}+{geometry.x}+{geometry.y}"
    )
    return geometry

