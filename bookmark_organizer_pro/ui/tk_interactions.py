"""Tk interaction helpers for custom controls."""

from __future__ import annotations

from typing import Callable


def _get_focus_color(fallback: str = "#5b8cff") -> str:
    try:
        from bookmark_organizer_pro.ui.widget_runtime import get_theme
        return get_theme().accent_primary
    except Exception:
        return fallback


def make_keyboard_activatable(
    widget,
    command: Callable[[], object],
    cursor: str = "hand2",
    focus_color: str = "",
):
    """Make a Tk widget respond like a small button.

    Several legacy surfaces use Labels as compact icon controls. This helper
    gives those widgets a focus target and keyboard activation while preserving
    the existing visual treatment.
    """
    if not focus_color:
        focus_color = _get_focus_color()
    if not callable(command):
        return widget

    def invoke(event=None):
        command()
        return "break"

    original_highlight = None
    original_thickness = 0
    try:
        original_highlight = widget.cget("highlightbackground")
    except Exception:
        original_highlight = None
    try:
        original_thickness = int(widget.cget("highlightthickness"))
    except Exception:
        original_thickness = 0

    try:
        widget.configure(cursor=cursor, takefocus=1)
        if original_thickness <= 0:
            original_highlight = widget.cget("bg")
            widget.configure(highlightthickness=1, highlightbackground=original_highlight)
        widget.configure(highlightcolor=focus_color)
    except Exception:
        pass

    def focus_in(event=None):
        try:
            widget.configure(highlightbackground=focus_color, highlightcolor=focus_color)
        except Exception:
            pass

    def focus_out(event=None):
        try:
            widget.configure(highlightbackground=original_highlight)
        except Exception:
            pass

    widget.bind("<Button-1>", invoke)
    widget.bind("<Return>", invoke)
    widget.bind("<KP_Enter>", invoke)
    widget.bind("<space>", invoke)
    widget.bind("<FocusIn>", focus_in, add="+")
    widget.bind("<FocusOut>", focus_out, add="+")
    return widget
