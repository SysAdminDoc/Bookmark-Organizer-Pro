"""Tk interaction helpers for custom controls."""

from __future__ import annotations

from typing import Callable


WHEEL_EVENTS = ("<MouseWheel>", "<Button-4>", "<Button-5>")


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
    accessible_name: str = "",
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
        try:
            widget.focus_set()
        except Exception:
            pass
        command()
        try:
            if widget.winfo_exists():
                widget.focus_set()
        except Exception:
            pass
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

    if not accessible_name:
        try:
            accessible_name = str(widget.cget("text")).strip()
        except Exception:
            accessible_name = ""
    widget._bop_accessible_name = accessible_name

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


def route_pointer_to_control(control, *children) -> None:
    """Route child pointer events through one semantic, focusable control."""
    control_tag = str(control)
    for child in children:
        if child is None:
            continue
        tags = list(child.bindtags())
        if control_tag not in tags:
            tags.insert(1, control_tag)
            child.bindtags(tuple(tags))


def wheel_scroll_units(event) -> int:
    """Normalize Windows, macOS, and Linux wheel events into scroll units."""
    button = getattr(event, "num", None)
    if button == 4:
        return -1
    if button == 5:
        return 1
    delta = getattr(event, "delta", 0)
    if not delta:
        return 0
    units = int(-delta / 120)
    return units or (-1 if delta > 0 else 1)


class ScopedMousewheelBinding:
    """Dispatch wheel events only when the pointer is inside one scroll host."""

    def __init__(self, host, callback: Callable[[int, object], object]):
        self.host = host
        self.callback = callback
        self.target = host.winfo_toplevel()
        self._bindings: dict[str, str] = {}
        for sequence in WHEEL_EVENTS:
            binding_id = self.target.bind(sequence, self._dispatch, add="+")
            if binding_id:
                self._bindings[sequence] = binding_id
        host.bind("<Destroy>", self._on_destroy, add="+")

    def _pointer_inside(self) -> bool:
        try:
            current = self.host.winfo_containing(*self.host.winfo_pointerxy())
            while current is not None:
                if current is self.host:
                    return True
                current = getattr(current, "master", None)
        except Exception:
            return False
        return False

    def _dispatch(self, event):
        if not self._pointer_inside():
            return None
        units = wheel_scroll_units(event)
        if not units:
            return "break"
        self.callback(units, event)
        return "break"

    def _on_destroy(self, event) -> None:
        if event.widget is self.host:
            self.close()

    def close(self) -> None:
        for sequence, binding_id in self._bindings.items():
            try:
                self.target.unbind(sequence, binding_id)
            except Exception:
                pass
        self._bindings.clear()


def bind_scoped_mousewheel(host, callback: Callable[[int, object], object]):
    """Bind a cross-platform wheel callback without process-global bind_all."""
    return ScopedMousewheelBinding(host, callback)
