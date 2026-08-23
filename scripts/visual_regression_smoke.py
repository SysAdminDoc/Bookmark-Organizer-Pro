"""Local visual smoke checks for desktop and extension surfaces.

The script captures screenshots into a temporary output directory by default.
It intentionally avoids the user's live bookmark library by running the desktop
app against a temporary BOOKMARK_DATA_DIR unless --data-dir is supplied.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.contract_runtime import ScriptWatchdog

DEFAULT_OUTPUT_DIR = Path(tempfile.gettempdir()) / "bookmark-organizer-pro-visual-smoke"
DESKTOP_VIEWPORTS = (
    (1280, 720, 1.0),
    (1540, 980, 1.25),
    (1920, 1080, 1.0),
)

# The two GitHub themes are the shipped defaults; Solarized Dark is included
# because its surfaces sit closest to the AA floor, so a palette regression
# shows up there first. These three are rendered at every viewport and DPI.
DESKTOP_SMOKE_THEMES = ("github_dark", "github_light", "solarized_dark")

# R-122 checked the other nine themes as palette maths only, never as pixels.
# Each one now gets rendered once, at the scaled laptop viewport where clipping
# and overflow show up first, which is far cheaper than the full matrix.
THEME_SWEEP_VIEWPORT = (1540, 980, 1.25)


def theme_sweep_names() -> tuple[str, ...]:
    """Built-in themes that the deep matrix above does not already cover."""
    from bookmark_organizer_pro.theme_runtime import BUILT_IN_THEMES

    return tuple(
        name for name in BUILT_IN_THEMES if name not in DESKTOP_SMOKE_THEMES
    )


@dataclass(frozen=True)
class ExtensionSurface:
    name: str
    html_file: str
    viewport: tuple[int, int]
    color_scheme: str
    expected_text: tuple[str, ...]
    click_selector: str = ""


DESKTOP_SURFACES = (
    "desktop-main-empty-dark",
    "desktop-main-list-dark",
    "desktop-search-error-dark",
    "desktop-main-list-light",
    "desktop-bookmark-editor-1280x720",
    "desktop-about-1280x720",
    "desktop-support-bundle-preview",
    "desktop-dependency-repair-1280x720",
    "desktop-assistant-settings",
    "desktop-access-credentials",
    "desktop-import-progress",
    "desktop-import-center",
    "desktop-cleanup-review",
    "desktop-read-later-queue",
    "desktop-snapshot-failures-sidebar",
    "desktop-export-dialog",
    "desktop-reader-view",
    "desktop-highlights-workspace",
    "desktop-organization-rules",
    "desktop-reader-highlight-deleted",
    "desktop-reader-orphaned-highlight",
    "desktop-graph-view",
)

EXTENSION_SURFACES = (
    ExtensionSurface(
        "extension-popup-dark",
        "popup.html",
        (380, 620),
        "dark",
        ("Save Bookmark", "Category", "Read Later"),
    ),
    ExtensionSurface(
        "extension-popup-light",
        "popup.html",
        (380, 620),
        "light",
        ("Save Bookmark", "Options", "Read Later"),
    ),
    ExtensionSurface(
        "extension-options-light",
        "options.html",
        (560, 620),
        "light",
        ("Local API", "Save Settings", "Test API"),
    ),
    ExtensionSurface(
        "extension-sidepanel-recent-dark",
        "sidepanel.html",
        (430, 760),
        "dark",
        ("Recent", "Search", "Connected", "Options", "Visual QA Handbook"),
    ),
    ExtensionSurface(
        "extension-sidepanel-add-light",
        "sidepanel.html",
        (430, 760),
        "light",
        ("Add", "Read Later", "Save Bookmark"),
        click_selector='button[data-tab="add"]',
    ),
    ExtensionSurface(
        "extension-popup-200pct-dark",
        "popup.html",
        (220, 760),
        "dark",
        ("Save Bookmark", "Category", "Read Later"),
    ),
    ExtensionSurface(
        "extension-sidepanel-search-200pct-light",
        "sidepanel.html",
        (220, 760),
        "light",
        ("Search", "Enter a query to search bookmarks."),
        click_selector='button[data-tab="search"]',
    ),
)


@dataclass(frozen=True)
class CaptureResult:
    name: str
    path: Path
    width: int
    height: int


class VisualSmokeError(AssertionError):
    """Raised when a visual smoke surface fails its contract."""


def _background_position(
    virtual_desktop: tuple[int, int, int, int], width: int, height: int
) -> tuple[int, int]:
    """Place a capture window completely left of the virtual desktop."""
    left, top, _desktop_width, desktop_height = virtual_desktop
    return left - max(1, width) - 128, top + max(0, (desktop_height - height) // 2)


def _virtual_desktop_bounds() -> tuple[int, int, int, int]:
    if os.name != "nt":
        return (0, 0, 1920, 1080)
    user32 = ctypes.windll.user32
    return (
        user32.GetSystemMetrics(76),
        user32.GetSystemMetrics(77),
        user32.GetSystemMetrics(78),
        user32.GetSystemMetrics(79),
    )


def _get_toplevel_hwnd(window) -> int:
    """Resolve Tk's client handle to the native top-level window handle."""
    window.update_idletasks()
    hwnd = int(window.winfo_id())
    if os.name == "nt":
        hwnd = int(ctypes.windll.user32.GetAncestor(hwnd, 2)) or hwnd
    return hwnd


def _prepare_background_window(window) -> int:
    """Map a Windows Tk window offscreen without activating or taskbar noise."""
    if os.name != "nt":
        window.deiconify()
        window.update_idletasks()
        return _get_toplevel_hwnd(window)

    user32 = ctypes.windll.user32
    window.update_idletasks()
    owner = getattr(window, "master", None)
    if owner is not None and not hasattr(owner, "wm_state"):
        owner = None
    client_hwnd = int(window.winfo_id())
    hwnd = _get_toplevel_hwnd(window)
    if user32.IsWindowVisible(hwnd):
        window.update_idletasks()
        window.update()
        user32.RedrawWindow(hwnd, None, None, 0x0001 | 0x0080 | 0x0100)
        user32.UpdateWindow(hwnd)
        return hwnd
    min_width, min_height = window.minsize()
    width = max(window.winfo_width(), window.winfo_reqwidth(), min_width, 240)
    height = max(window.winfo_height(), window.winfo_reqheight(), min_height, 180)
    x, y = _background_position(_virtual_desktop_bounds(), width, height)

    gwl_exstyle = -20
    ws_ex_toolwindow = 0x00000080
    ws_ex_appwindow = 0x00040000
    ws_ex_noactivate = 0x08000000
    style = int(user32.GetWindowLongW(hwnd, gwl_exstyle))
    style = (style | ws_ex_toolwindow | ws_ex_noactivate) & ~ws_ex_appwindow
    user32.SetWindowLongW(hwnd, gwl_exstyle, style)
    swp_nozorder = 0x0004
    swp_noactivate = 0x0010
    swp_showwindow = 0x0040
    if hwnd != client_hwnd:
        try:
            window.attributes("-topmost", False)
        except Exception:
            pass
    insert_after = -2 if hwnd != client_hwnd else 0
    flags = swp_noactivate
    if hwnd == client_hwnd:
        flags |= swp_nozorder
    if owner is None:
        flags |= swp_showwindow
    positioned = user32.SetWindowPos(hwnd, insert_after, x, y, width, height, flags)
    if not positioned and hwnd == client_hwnd:
        raise VisualSmokeError("could not position background capture window")
    if owner is not None:
        _prepare_background_window(owner)
    user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
    for _ in range(8):
        window.update_idletasks()
        window.update()
        if user32.IsWindowVisible(hwnd):
            break
        time.sleep(0.01)
    if not user32.IsWindowVisible(hwnd):
        raise VisualSmokeError("background capture window did not map")
    user32.RedrawWindow(hwnd, None, None, 0x0001 | 0x0080 | 0x0100)
    user32.UpdateWindow(hwnd)
    window.update()
    return hwnd


def _capture_background_window(window, hwnd: int):
    """Capture a mapped HWND directly, independent of desktop occlusion."""
    from PIL import ImageGrab, ImageWin

    if os.name != "nt":
        x = window.winfo_rootx()
        y = window.winfo_rooty()
        return ImageGrab.grab(
            bbox=(x, y, x + window.winfo_width(), y + window.winfo_height())
        )

    image = ImageGrab.grab(window=ImageWin.HWND(hwnd))
    user32 = ctypes.windll.user32
    window_rect = wintypes.RECT()
    client_rect = wintypes.RECT()
    client_origin = wintypes.POINT(0, 0)
    if not user32.GetWindowRect(hwnd, ctypes.byref(window_rect)):
        raise VisualSmokeError("could not read capture window bounds")
    if not user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
        raise VisualSmokeError("could not read capture client bounds")
    user32.ClientToScreen(hwnd, ctypes.byref(client_origin))
    client_width = max(1, client_rect.right - client_rect.left)
    client_height = max(1, client_rect.bottom - client_rect.top)
    if image.size == (client_width, client_height):
        return image
    left = max(0, client_origin.x - window_rect.left)
    top = max(0, client_origin.y - window_rect.top)
    right = left + client_width
    bottom = top + client_height
    return image.crop((left, top, right, bottom))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture and validate local visual smoke screenshots.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="directory for captured PNG files")
    parser.add_argument("--data-dir", type=Path, default=None, help="desktop app data dir; defaults to a temp dir")
    parser.add_argument(
        "--surface",
        choices=("all", "desktop", "extension"),
        default="all",
        help="surface group to capture",
    )
    parser.add_argument("--total-timeout", type=float, default=300.0)
    parser.add_argument("--phase-timeout", type=float, default=180.0)
    return parser.parse_args(argv)


def set_process_dpi_aware() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def assert_image_healthy(path: Path, *, min_width: int = 240, min_height: int = 180) -> tuple[int, int]:
    from PIL import Image, ImageStat

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        if width < min_width or height < min_height:
            raise VisualSmokeError(f"{path.name} is too small: {width}x{height}")

        extrema = rgb.getextrema()
        if all(high - low < 8 for low, high in extrema):
            raise VisualSmokeError(f"{path.name} appears blank: low color range")

        stat = ImageStat.Stat(rgb)
        if max(stat.stddev) < 2.0:
            raise VisualSmokeError(f"{path.name} appears blank: low variance")

        sample = rgb.resize((min(width, 180), min(height, 180)))
        pixels = sample.get_flattened_data() if hasattr(sample, "get_flattened_data") else sample.getdata()
        if len(set(pixels)) < 16:
            raise VisualSmokeError(f"{path.name} appears blank: too few colors")

        return width, height


def collect_tk_text(widget) -> str:
    parts: list[str] = []

    def visit(current) -> None:
        try:
            text = current.cget("text")
            if text:
                parts.append(str(text))
        except Exception:
            pass

        try:
            if current.winfo_class() == "Text":
                text = current.get("1.0", "end").strip()
                if text:
                    parts.append(text)
            elif current.winfo_class() == "Listbox":
                for index in range(current.size()):
                    parts.append(str(current.get(index)))
            elif current.winfo_class() == "Canvas":
                for item in current.find_all():
                    if current.type(item) == "text":
                        text = current.itemcget(item, "text")
                        if text:
                            parts.append(str(text))
        except Exception:
            pass

        try:
            if current.winfo_class() == "Treeview":
                columns = ("#0", *tuple(current["columns"]))
                for column in columns:
                    heading = current.heading(column, "text")
                    if heading:
                        parts.append(str(heading))
                for item in current.get_children(""):
                    text = current.item(item, "text")
                    if text:
                        parts.append(str(text))
                    parts.extend(str(value) for value in current.item(item, "values"))
        except Exception:
            pass

        try:
            children = current.winfo_children()
        except Exception:
            children = []
        for child in children:
            visit(child)

    visit(widget)
    return "\n".join(parts)


def require_text(surface: str, text_blob: str, expected: Iterable[str]) -> None:
    missing = [text for text in expected if text not in text_blob]
    if missing:
        raise VisualSmokeError(f"{surface} is missing expected text: {', '.join(missing)}")


def capture_tk_window(window, output_dir: Path, name: str, expected_text: Iterable[str]) -> CaptureResult:
    hwnd = _prepare_background_window(window)

    text_blob = collect_tk_text(window)
    require_text(name, text_blob, expected_text)

    output_path = output_dir / f"{name}.png"
    image = _capture_background_window(window, hwnd)
    width, height = image.size
    if width < 240 or height < 180:
        raise VisualSmokeError(f"{name} window is too small: {width}x{height}")
    image.save(output_path)
    owner = getattr(window, "master", None)
    try:
        if owner is not None:
            window.withdraw()
        if owner is not None and hasattr(owner, "withdraw"):
            owner.withdraw()
    except Exception:
        pass
    width, height = assert_image_healthy(output_path)
    return CaptureResult(name, output_path, width, height)


def destroy_window(window) -> None:
    try:
        window.withdraw()
        window.update_idletasks()
    except Exception:
        pass
    try:
        window.grab_release()
    except Exception:
        pass
    try:
        window.destroy()
    except Exception:
        pass


def assert_actionable_controls_inside(window) -> None:
    """Fail when a visible actionable widget is partially clipped by the client area."""
    window.update_idletasks()
    left = window.winfo_rootx()
    top = window.winfo_rooty()
    right = left + window.winfo_width()
    bottom = top + window.winfo_height()
    failures: list[str] = []
    stack = list(window.winfo_children())
    while stack:
        widget = stack.pop()
        stack.extend(widget.winfo_children())
        if not widget.winfo_ismapped() or widget.winfo_width() <= 1 or widget.winfo_height() <= 1:
            continue
        widget_left = widget.winfo_rootx()
        widget_top = widget.winfo_rooty()
        widget_right = widget_left + widget.winfo_width()
        widget_bottom = widget_top + widget.winfo_height()
        if widget_right <= left or widget_left >= right or widget_bottom <= top or widget_top >= bottom:
            continue
        takefocus = str(widget.cget("takefocus")) if "takefocus" in widget.keys() else ""
        cursor = str(widget.cget("cursor")) if "cursor" in widget.keys() else ""
        actionable = takefocus not in {"", "0", "false"} or cursor == "hand2"
        if not actionable:
            continue
        chrome_tolerance = 8
        horizontal_clip = widget_left < left - chrome_tolerance or widget_right > right + chrome_tolerance
        vertical_clip = widget_top < top - chrome_tolerance or widget_bottom > bottom + chrome_tolerance
        ancestor = widget.master
        inside_scroll_viewport = False
        while ancestor is not None and ancestor is not window:
            if ancestor.winfo_class() == "Canvas":
                inside_scroll_viewport = True
                break
            ancestor = getattr(ancestor, "master", None)
        if horizontal_clip or (vertical_clip and not inside_scroll_viewport):
            text = str(widget.cget("text")) if "text" in widget.keys() else ""
            failures.append(
                f"{widget.winfo_class()}:{widget.winfo_name()}:{text!r} "
                f"({widget_left - left},{widget_top - top},{widget.winfo_width()}x{widget.winfo_height()})"
            )
    if failures:
        raise VisualSmokeError("actionable controls clipped: " + ", ".join(failures[:8]))


def assert_named_controls_visible(window, expected_labels: Iterable[str]) -> None:
    """Require named controls to be mapped and fully inside the client area."""
    window.update_idletasks()
    left = window.winfo_rootx()
    top = window.winfo_rooty()
    right = left + window.winfo_width()
    bottom = top + window.winfo_height()
    text_widgets: dict[str, list] = {label: [] for label in expected_labels}
    stack = list(window.winfo_children())
    while stack:
        widget = stack.pop()
        stack.extend(widget.winfo_children())
        if "text" not in widget.keys():
            continue
        text = str(widget.cget("text"))
        for label in expected_labels:
            if label in text:
                text_widgets[label].append(widget)

    failures: list[str] = []
    for label, widgets in text_widgets.items():
        visible = False
        states: list[str] = []
        for widget in widgets:
            states.append(
                f"{widget.winfo_class()} mapped={widget.winfo_ismapped()} "
                f"at {widget.winfo_rootx() - left},{widget.winfo_rooty() - top} "
                f"size {widget.winfo_width()}x{widget.winfo_height()}"
            )
            if not widget.winfo_ismapped() or widget.winfo_width() <= 1 or widget.winfo_height() <= 1:
                continue
            widget_left = widget.winfo_rootx()
            widget_top = widget.winfo_rooty()
            widget_right = widget_left + widget.winfo_width()
            widget_bottom = widget_top + widget.winfo_height()
            if (
                widget_left >= left
                and widget_top >= top
                and widget_right <= right
                and widget_bottom <= bottom
            ):
                visible = True
                break
        if not visible:
            detail = "; ".join(states) if states else "not found"
            failures.append(f"{label} ({detail})")
    if failures:
        raise VisualSmokeError(
            "named controls not visible: " + ", ".join(failures)
        )


def assert_realized_viewport(window, width: int, height: int) -> None:
    """Require Tk to honor the requested client viewport exactly."""
    actual = (window.winfo_width(), window.winfo_height())
    expected = (int(width), int(height))
    if actual != expected:
        raise VisualSmokeError(f"viewport realized as {actual[0]}x{actual[1]}, expected {width}x{height}")


def assert_no_horizontal_overflow(window) -> None:
    """Fail when mapped widget geometry forces content past the client width."""
    window.update_idletasks()
    left = window.winfo_rootx()
    right = left + window.winfo_width()
    tolerance = 8
    failures: list[str] = []
    stack = list(window.winfo_children())
    while stack:
        widget = stack.pop()
        stack.extend(widget.winfo_children())
        if not widget.winfo_ismapped() or widget.winfo_width() <= 1:
            continue
        widget_left = widget.winfo_rootx()
        widget_right = widget_left + widget.winfo_width()
        if widget_left < left - tolerance or widget_right > right + tolerance:
            text = str(widget.cget("text")) if "text" in widget.keys() else ""
            failures.append(
                f"{widget.winfo_class()}:{widget.winfo_name()}:{text!r} "
                f"x={widget_left - left} width={widget.winfo_width()}"
            )
    if failures:
        raise VisualSmokeError("horizontal overflow: " + ", ".join(failures[:8]))


def _widget_bounds(widget) -> tuple[int, int, int, int]:
    return (
        widget.winfo_rootx(),
        widget.winfo_rooty(),
        widget.winfo_rootx() + widget.winfo_width(),
        widget.winfo_rooty() + widget.winfo_height(),
    )


def assert_widget_inside(window, widget, label: str) -> None:
    """Require a mapped widget to remain inside its top-level client area."""
    window.update_idletasks()
    if not widget.winfo_ismapped() or widget.winfo_width() <= 1 or widget.winfo_height() <= 1:
        raise VisualSmokeError(f"{label} is not mapped with usable geometry")
    window_left, window_top, window_right, window_bottom = _widget_bounds(window)
    widget_left, widget_top, widget_right, widget_bottom = _widget_bounds(widget)
    if not (
        window_left <= widget_left
        and window_top <= widget_top
        and widget_right <= window_right
        and widget_bottom <= window_bottom
    ):
        raise VisualSmokeError(
            f"{label} escapes window: "
            f"({widget_left - window_left},{widget_top - window_top},"
            f"{widget.winfo_width()}x{widget.winfo_height()})"
        )


def assert_widgets_do_not_overlap(first, second, label: str, *, gap: int = 0) -> None:
    """Require two layout regions to have a clear separation."""
    first_left, first_top, first_right, first_bottom = _widget_bounds(first)
    second_left, second_top, second_right, second_bottom = _widget_bounds(second)
    if not (
        first_right + gap <= second_left
        or second_right + gap <= first_left
        or first_bottom + gap <= second_top
        or second_bottom + gap <= first_top
    ):
        raise VisualSmokeError(f"{label} regions overlap")


def assert_graph_labels_visible(dialog) -> None:
    """Require every graph label to fit the scroll region without collisions."""
    labels = dialog.canvas.find_withtag("node-label")
    if len(labels) != len(dialog.graph.nodes):
        raise VisualSmokeError(
            f"graph label count mismatch: {len(labels)} != {len(dialog.graph.nodes)}"
        )
    boxes: list[tuple[int, int, int, int]] = []
    for item in labels:
        bbox = dialog.canvas.bbox(item)
        if not bbox:
            raise VisualSmokeError("graph label has no measurable bounds")
        left, top, right, bottom = bbox
        if left < 4 or top < 4 or right > dialog.graph_width - 4 or bottom > dialog.graph_height - 4:
            raise VisualSmokeError(f"graph label clips at {bbox}")
        for other in boxes:
            if not (
                right <= other[0]
                or other[2] <= left
                or bottom <= other[1]
                or other[3] <= top
            ):
                raise VisualSmokeError(f"graph labels overlap at {bbox} and {other}")
        boxes.append(bbox)


def assert_combobox_uses_theme(combo, theme) -> None:
    """Fail when a combobox falls back to an unthemed white native field."""
    from tkinter import ttk

    style = ttk.Style(combo)
    style_name = combo.cget("style") or "TCombobox"
    field_color = style.lookup(style_name, "fieldbackground")
    expected = {
        str(theme.bg_primary).lower(),
        str(theme.bg_secondary).lower(),
        str(theme.bg_card).lower(),
    }
    if not field_color or str(field_color).lower() not in expected:
        raise VisualSmokeError(
            f"combobox field is not using theme tokens: {field_color!r}"
        )


def _set_scaling(window, baseline: float, multiplier: float) -> None:
    window.tk.call("tk", "scaling", baseline * multiplier)


def _verify_viewport(window, width: int, height: int) -> None:
    window.geometry(f"{width}x{height}")
    window.update_idletasks()
    window.update()
    assert_realized_viewport(window, width, height)
    assert_actionable_controls_inside(window)
    assert_no_horizontal_overflow(window)


def focusable_widgets(window) -> list:
    """Every mapped widget under `window` that opts into keyboard focus."""
    found = []
    stack = list(window.winfo_children())
    while stack:
        widget = stack.pop()
        stack.extend(widget.winfo_children())
        if not widget.winfo_ismapped():
            continue
        if widget.winfo_width() <= 1 or widget.winfo_height() <= 1:
            continue
        if "takefocus" not in widget.keys():
            continue
        if str(widget.cget("takefocus")) not in {"1", "true"}:
            continue
        found.append(widget)
    return found


def _tab_ring(start, limit: int) -> set:
    """Widget paths reachable by following Tab from `start` until it cycles."""
    seen: set[str] = set()
    current = start
    for _ in range(limit):
        key = str(current)
        if key in seen:
            return seen
        seen.add(key)
        following = current.tk_focusNext()
        if following is None:
            return seen
        current = following
    raise VisualSmokeError("keyboard traversal did not return to its starting point")


def assert_keyboard_traversal_reaches_every_control(window) -> None:
    """Follow Tab all the way round and prove no control is stranded off the ring.

    The accessibility contract checks controls one at a time: focusable, fires
    once, restores focus. A control can pass all of that and still be
    unreachable, because Tab follows Tk's ring and that ring does not cross
    between toplevels. A control parented onto a leaked or stray toplevel is
    mapped, is focusable, and no amount of tabbing in the main window will ever
    land on it.

    Each toplevel is walked from its own first control, so the failure names
    the widgets that are actually stranded rather than whichever group the walk
    happened not to start in.
    """
    window.update_idletasks()
    controls = focusable_widgets(window)
    if not controls:
        raise VisualSmokeError("no focusable controls found in the main window")

    by_toplevel: dict[str, list] = {}
    for widget in controls:
        by_toplevel.setdefault(str(widget.winfo_toplevel()), []).append(widget)

    stranded: list[str] = []
    for group in by_toplevel.values():
        reached = _tab_ring(group[0], len(group) * 4 + 32)
        stranded.extend(str(widget) for widget in group if str(widget) not in reached)

    extra = sorted(name for name in by_toplevel if name != str(window))
    if extra:
        stranded.extend(
            f"{name} (a separate toplevel, unreachable from the main window)"
            for name in extra
        )

    if stranded:
        shown = sorted(stranded)
        raise VisualSmokeError(
            "Tab never reaches "
            + ", ".join(shown[:5])
            + (f" and {len(shown) - 5} more" if len(shown) > 5 else "")
        )


def _painted_background(window) -> str:
    """The background Tk actually resolved for the window's largest frame.

    Read from the realized widget rather than from the palette, so a theme that
    computes a colour but never applies it is not mistaken for one that does.
    """
    best = ""
    best_area = -1
    stack = list(window.winfo_children())
    while stack:
        widget = stack.pop()
        stack.extend(widget.winfo_children())
        if not widget.winfo_ismapped() or "background" not in widget.keys():
            continue
        area = widget.winfo_width() * widget.winfo_height()
        if area > best_area:
            best_area = area
            best = str(widget.cget("background"))
    return best or str(window.cget("background"))


def verify_desktop_viewports(
    root, theme_manager, *, collapsible_rail=None, output_dir: Path | None = None
) -> None:
    """Exercise supported desktop sizes and themes without foreground activation."""
    _prepare_background_window(root)
    baseline = float(root.tk.call("tk", "scaling"))
    try:
        for width, height, scaling in DESKTOP_VIEWPORTS:
            for theme_name in DESKTOP_SMOKE_THEMES:
                _set_scaling(root, baseline, scaling)
                theme_manager.set_theme(theme_name)
                _verify_viewport(root, width, height)
                if collapsible_rail is not None:
                    rail = collapsible_rail() if callable(collapsible_rail) else collapsible_rail
                    rail_visible = bool(rail.winfo_manager())
                    if width < 1400 and rail_visible:
                        raise VisualSmokeError("right rail did not collapse at laptop width")
                    if width >= 1400 and not rail_visible:
                        raise VisualSmokeError("right rail did not restore at wide viewport")
        sweep_width, sweep_height, sweep_scaling = THEME_SWEEP_VIEWPORT
        painted: dict[str, str] = {}
        for theme_name in theme_sweep_names():
            _set_scaling(root, baseline, sweep_scaling)
            # The return value is the difference between rendering this theme
            # and silently rendering the previous one, so it is not dropped.
            if not theme_manager.set_theme(theme_name):
                raise VisualSmokeError(f"theme {theme_name} could not be applied")
            _verify_viewport(root, sweep_width, sweep_height)
            painted[theme_name] = _painted_background(root)
            if output_dir is not None:
                # Geometry checks cannot see colour. A capture runs the pixel
                # health check, which is what catches a palette that renders
                # the window blank.
                capture_tk_window(root, output_dir, f"desktop-theme-{theme_name}", ())
                _prepare_background_window(root)
        distinct = len(set(painted.values()))
        if distinct < 2:
            raise VisualSmokeError(
                "every swept theme painted the same background "
                f"({sorted(set(painted.values()))}); the theme is not reaching the window"
            )
        assert_keyboard_traversal_reaches_every_control(root)
    finally:
        _set_scaling(root, baseline, 1.0)
        root.withdraw()


def verify_graph_viewports(root, theme_manager, bookmarks) -> None:
    """Create Graph View in every supported viewport/theme/DPI combination."""
    from bookmark_organizer_pro.ui.graph_view import GraphViewDialog

    baseline = float(root.tk.call("tk", "scaling"))
    try:
        for width, height, scaling in DESKTOP_VIEWPORTS:
            for theme_name in ("github_dark", "github_light"):
                _set_scaling(root, baseline, scaling)
                theme_manager.set_theme(theme_name)
                dialog = GraphViewDialog(root, bookmarks)
                try:
                    _prepare_background_window(dialog)
                    _verify_viewport(dialog, width, height)
                    assert_graph_labels_visible(dialog)
                    assert_named_controls_visible(
                        dialog,
                        ("Bookmark Graph", "Legend", "Selected", "Arrow keys navigate"),
                    )
                    assert_widget_inside(dialog, dialog.status, "graph keyboard help")
                finally:
                    destroy_window(dialog)
    finally:
        _set_scaling(root, baseline, 1.0)


def verify_dialog_viewports(root, theme_manager, bookmark) -> None:
    """Exercise editor and About footer contracts at every supported viewport."""
    from bookmark_organizer_pro.ui.about import AboutDialog
    from bookmark_organizer_pro.ui.widget_bookmark_editor import BookmarkEditorDialog
    from bookmark_organizer_pro.ui.window_geometry import apply_screen_aware_geometry
    from bookmark_organizer_pro.theme_runtime import get_theme

    baseline = float(root.tk.call("tk", "scaling"))
    try:
        for width, height, scaling in DESKTOP_VIEWPORTS:
            for theme_name in ("github_dark", "github_light"):
                _set_scaling(root, baseline, scaling)
                theme_manager.set_theme(theme_name)
                editor = BookmarkEditorDialog(
                    root,
                    bookmark=bookmark,
                    categories=["Development", "Research"],
                )
                try:
                    apply_screen_aware_geometry(
                        editor,
                        640,
                        760,
                        screen_width=width,
                        screen_height=height,
                    )
                    _prepare_background_window(editor)
                    editor.update()
                    assert_actionable_controls_inside(editor)
                    assert_named_controls_visible(
                        editor,
                        ("Edit bookmark", "Save bookmark", "Cancel"),
                    )
                    assert_widget_inside(editor, editor.btn_frame, "bookmark editor footer")
                    assert_widgets_do_not_overlap(
                        editor.content_canvas,
                        editor.btn_frame,
                        "bookmark editor body/footer",
                    )
                    assert_combobox_uses_theme(editor.category_combo, get_theme())
                finally:
                    destroy_window(editor)

                about = AboutDialog(root)
                try:
                    apply_screen_aware_geometry(
                        about,
                        700,
                        640,
                        screen_width=width,
                        screen_height=height,
                    )
                    _prepare_background_window(about)
                    about.update()
                    assert_actionable_controls_inside(about)
                    assert_named_controls_visible(
                        about,
                        ("Open Logs", "Copy Diagnostics", "Preview Support Bundle", "Close"),
                    )
                    assert_widget_inside(about, about.footer, "about footer")
                finally:
                    destroy_window(about)
    finally:
        _set_scaling(root, baseline, 1.0)


def run_desktop_smoke(output_dir: Path, data_dir: Path) -> list[CaptureResult]:
    set_process_dpi_aware()
    os.environ["BOOKMARK_DATA_DIR"] = str(data_dir)

    import tkinter as tk

    from bookmark_organizer_pro.app import FinalBookmarkOrganizerApp
    from bookmark_organizer_pro.app_mixins.import_export import ImportProgressModal
    from bookmark_organizer_pro.constants import APP_DIR, ensure_directories
    from bookmark_organizer_pro.models import Bookmark
    from bookmark_organizer_pro.services.mcp_auth import (
        MCP_READ_SCOPE,
        MCPTokenManager,
    )
    from bookmark_organizer_pro.services.reader_annotations import ReaderAnnotationStore
    from bookmark_organizer_pro.services.snapshot import SnapshotBackendAttempt, SnapshotFailureStore
    from bookmark_organizer_pro.theme_runtime import get_theme, get_theme_manager
    from bookmark_organizer_pro.ui.graph_view import GraphViewDialog
    from bookmark_organizer_pro.ui.import_center import ImportCenterDialog, build_import_sources
    from bookmark_organizer_pro.ui.about import AboutDialog
    from bookmark_organizer_pro.ui.cleanup_review import CleanupReviewDialog, CleanupReviewGroup
    from bookmark_organizer_pro.ui.dependencies import DependencyCheckDialog
    from bookmark_organizer_pro.ui.read_later_queue import ReadLaterQueueDialog
    from bookmark_organizer_pro.ui.reader_view import ReaderViewDialog
    from bookmark_organizer_pro.ui.highlights_workspace import HighlightsWorkspaceDialog
    from bookmark_organizer_pro.ui.organization_rules import OrganizationRulesDialog
    from bookmark_organizer_pro.services.organization_rules import OrganizationRule, OrganizationRulesService
    from bookmark_organizer_pro.ui.treeview import (
        SortableTreeview,
        save_accessible_list_mode,
    )
    from bookmark_organizer_pro.ui.widget_bookmark_editor import BookmarkEditorDialog
    from bookmark_organizer_pro.ui.window_geometry import apply_screen_aware_geometry
    from bookmark_organizer_pro.ui.workflow_selective_export import SelectiveExportDialog
    from bookmark_organizer_pro.utils.dependencies import DependencyManager

    ensure_directories()
    root = tk.Tk()
    root.withdraw()
    root.geometry("1540x980")
    root.title("Bookmark Organizer Pro Visual Smoke")
    app = FinalBookmarkOrganizerApp(root)
    root.update()
    theme_manager = get_theme_manager()
    verify_desktop_viewports(
        root,
        theme_manager,
        collapsible_rail=lambda: app._right_sidebar,
        output_dir=output_dir,
    )
    root.geometry("1540x980")
    theme_manager.set_theme("github_dark")
    root.update()

    results: list[CaptureResult] = []
    try:
        empty_table = app.tree.semantic_snapshot()
        if empty_table["state"] != "empty" or empty_table["rows"]:
            raise VisualSmokeError("empty library is missing semantic table state")
        results.append(
            capture_tk_window(
                root,
                output_dir,
                "desktop-main-empty-dark",
                (
                    "Bookmark Organizer Pro",
                    "Build a library worth returning to",
                    "Quick start",
                    "Focus",
                    "Select a bookmark",
                ),
            )
        )

        editor = BookmarkEditorDialog(
            root,
            bookmark=Bookmark(
                id=504,
                url="https://example.com/editor",
                title="Editor viewport fixture",
                category="Development",
                tags=["viewport"],
                ai_tags=["accessibility", "qa"],
                ai_confidence=0.9,
                description="A long-form fixture that exercises the scrollable editor body.",
            ),
            categories=["Development", "Research"],
        )
        apply_screen_aware_geometry(
            editor, 640, 760, screen_width=1280, screen_height=720,
        )
        editor.update()
        _prepare_background_window(editor)
        assert_actionable_controls_inside(editor)
        assert_named_controls_visible(editor, ("Edit bookmark", "Save bookmark", "Cancel"))
        assert_widget_inside(editor, editor.btn_frame, "bookmark editor footer")
        assert_widgets_do_not_overlap(
            editor.content_canvas,
            editor.btn_frame,
            "bookmark editor body/footer",
        )
        assert_combobox_uses_theme(editor.category_combo, get_theme())
        results.append(
            capture_tk_window(
                editor,
                output_dir,
                "desktop-bookmark-editor-1280x720",
                ("Edit bookmark", "BOOKMARK DETAILS", "Save bookmark"),
            )
        )
        editor.destroy()

        about = AboutDialog(root)
        apply_screen_aware_geometry(
            about, 700, 640, screen_width=1280, screen_height=720,
        )
        about.update()
        _prepare_background_window(about)
        assert_actionable_controls_inside(about)
        assert_named_controls_visible(
            about,
            ("Open Logs", "Copy Diagnostics", "Preview Support Bundle", "Close"),
        )
        assert_widget_inside(about, about.footer, "about footer")
        results.append(
            capture_tk_window(
                about,
                output_dir,
                "desktop-about-1280x720",
                ("Bookmark Organizer Pro", "Version"),
            )
        )
        about.deiconify()
        about.update()
        about._export_support_bundle()
        support_preview = next(
            child for child in about.winfo_children()
            if isinstance(child, tk.Toplevel)
        )
        support_preview.update()
        assert_actionable_controls_inside(support_preview)
        assert_named_controls_visible(support_preview, ("Save Bundle", "Cancel"))
        results.append(
            capture_tk_window(
                support_preview,
                output_dir,
                "desktop-support-bundle-preview",
                (
                    "Review the exact files before saving",
                    "diagnostics.json",
                    "Save Bundle",
                ),
            )
        )
        destroy_window(support_preview)
        about.destroy()

        dependencies = DependencyManager()
        dependencies.check_all()
        dependencies.missing_required = ["regex"]
        dependency_dialog = DependencyCheckDialog(root, dependencies)
        apply_screen_aware_geometry(
            dependency_dialog, 640, 500, screen_width=1280, screen_height=720,
        )
        _prepare_background_window(dependency_dialog)
        assert_actionable_controls_inside(dependency_dialog)
        assert_named_controls_visible(
            dependency_dialog,
            ("Setup Check", "Required: regex", "exact Python environment", "Close"),
        )
        assert_widget_inside(dependency_dialog, dependency_dialog.footer, "dependency dialog footer")
        assert_widgets_do_not_overlap(
            dependency_dialog.content,
            dependency_dialog.footer,
            "dependency dialog body/footer",
        )
        results.append(
            capture_tk_window(
                dependency_dialog,
                output_dir,
                "desktop-dependency-repair-1280x720",
                ("Setup Check", "Required: regex", "exact Python environment", "Close"),
            )
        )
        dependency_dialog.destroy()

        sample_bookmarks = [
            Bookmark(
                id=501,
                url="https://example.com/visual-regression",
                title="Visual Regression Guide",
                description="A practical handbook for stable desktop screenshot testing.",
                category="Development",
                tags=["qa", "desktop"],
                is_pinned=True,
                read_later=True,
                created_at="2026-07-12T09:00:00",
            ),
            Bookmark(
                id=502,
                url="https://docs.python.org/3/library/tkinter.html",
                title="Tkinter Reference",
                description="Native desktop widgets, layout, events, and accessibility.",
                category="Development",
                tags=["python"],
                visit_count=2,
                created_at="2026-07-10T09:00:00",
            ),
            Bookmark(
                id=503,
                url="https://developer.chrome.com/docs/extensions",
                title="Extension Platform Notes",
                description="Manifest V3 service workers, side panels, and storage contracts.",
                category="Browsers",
                tags=["extension"],
                created_at="2026-07-11T09:00:00",
            ),
        ]
        verify_dialog_viewports(root, theme_manager, sample_bookmarks[0])
        for bookmark in sample_bookmarks:
            app.bookmark_manager.add_bookmark(bookmark, save=False)
        app.bookmark_manager.save_bookmarks()
        app._refresh_all()
        app.tree.selection_set("502", emit=False)
        app.selected_bookmarks = [502]
        app._update_right_rail_selection()
        app.tree.sort_by_column("saved")
        if (
            list(app.tree.get_children()) != ["502", "503", "501"]
            or app.tree.selection() != ("502",)
            or app.selected_bookmarks != [502]
        ):
            raise VisualSmokeError(
                "typed ascending date sort lost order or selection: "
                f"rows={list(app.tree.get_children())!r} "
                f"selection={app.tree.selection()!r} "
                f"app_selection={app.selected_bookmarks!r}"
            )
        app._refresh_bookmark_list()
        if (
            list(app.tree.get_children()) != ["502", "503", "501"]
            or app.tree.selection() != ("502",)
        ):
            raise VisualSmokeError(
                "refresh lost active sort or selected row: "
                f"rows={list(app.tree.get_children())!r} "
                f"selection={app.tree.selection()!r} "
                f"app_selection={app.selected_bookmarks!r}"
            )
        app.tree.sort_by_column("saved")
        semantic_table = app.tree.semantic_snapshot()
        if (
            list(app.tree.get_children()) != ["501", "503", "502"]
            or [header["label"] for header in semantic_table["headers"]]
            != ["Site", "Title", "Collection / Tags", "Saved", "Status", "Pinned"]
            or semantic_table["headers"][3]["sort"] != "descending"
            or semantic_table["rows"][2]["position"] != 3
            or not semantic_table["rows"][2]["selected"]
        ):
            raise VisualSmokeError(
                "virtual table semantic state diverges from sorted visible rows"
            )

        verify_desktop_viewports(
        root,
        theme_manager,
        collapsible_rail=lambda: app._right_sidebar,
        output_dir=output_dir,
    )
        if app.tree.selection() != ("502",) or app.selected_bookmarks != [502]:
            raise VisualSmokeError(
                "theme and viewport reconstruction lost table selection: "
                f"selection={app.tree.selection()!r} "
                f"app_selection={app.selected_bookmarks!r}"
            )
        root.geometry("1540x980")
        theme_manager.set_theme("github_dark")
        root.update()
        results.append(
            capture_tk_window(
                root,
                output_dir,
                "desktop-main-list-dark",
                ("Bookmark Organizer Pro", "Visual Regression Guide", "Focus", "Tkinter Reference"),
            )
        )

        app.search_var.set("unknown:value")
        app._refresh_bookmark_list()
        root.update()
        if (
            app.search_frame.cget("highlightbackground")
            != theme_manager.current_theme.colors.accent_error
        ):
            raise VisualSmokeError("invalid search did not expose an error border")
        search_table = app.tree.semantic_snapshot()
        if (
            search_table["state"] != "error"
            or "errors" not in search_table["message"].lower()
        ):
            raise VisualSmokeError("invalid search is missing semantic error state")
        results.append(
            capture_tk_window(
                root,
                output_dir,
                "desktop-search-error-dark",
                (
                    "Bookmark Organizer Pro",
                    "Search error: Column 1: Unknown search field 'unknown'.",
                    "No bookmarks match this view",
                ),
            )
        )
        app._clear_search()
        app.tree.selection_set("502", emit=False)
        app.selected_bookmarks = [502]
        app._update_right_rail_selection()
        root.update()

        theme_manager.set_theme("github_light")
        root.update()
        results.append(
            capture_tk_window(
                root,
                output_dir,
                "desktop-main-list-light",
                ("Bookmark Organizer Pro", "Library", "Focus", "Tkinter Reference"),
            )
        )

        save_accessible_list_mode(True)
        theme_manager.set_theme("github_dark")
        root.update()
        if not isinstance(app.tree, SortableTreeview):
            raise VisualSmokeError(
                "accessible preference did not rebuild the library as a native table"
            )
        native_table = app.tree.semantic_snapshot()
        if (
            [row["id"] for row in native_table["rows"]] != ["501", "503", "502"]
            or native_table["headers"][3]["sort"] != "descending"
            or not native_table["rows"][2]["selected"]
        ):
            raise VisualSmokeError(
                "native table diverges from virtual sort or selection semantics: "
                f"rows={[row['id'] for row in native_table['rows']]!r} "
                f"sort={native_table['headers'][3]['sort']!r} "
                f"selected={[row['id'] for row in native_table['rows'] if row['selected']]!r}"
            )
        results.append(
            capture_tk_window(
                root,
                output_dir,
                "desktop-main-list-accessible-dark",
                (
                    "Bookmark Organizer Pro",
                    "Site",
                    "Pinned",
                    "Saved",
                    "Tkinter Reference",
                ),
            )
        )
        save_accessible_list_mode(False)
        app._apply_theme_live()
        root.update()

        SnapshotFailureStore().record_failure(
            sample_bookmarks[1],
            "All snapshot backends failed",
            (SnapshotBackendAttempt("python", False, "fetch failed: visual smoke"),),
        )
        app._refresh_all()
        root.update()
        app._view_snapshot_failures()
        snapshot_report = root.winfo_children()[-1]
        results.append(
            capture_tk_window(
                snapshot_report,
                output_dir,
                "desktop-snapshot-failures-sidebar",
                ("Snapshot Failure Report", "failed snapshot", "Retry Failed"),
            )
        )
        destroy_window(snapshot_report)

        root.withdraw()
        theme_manager.set_theme("github_dark")
        root.update()
        app._show_ai_settings()
        assistant = root.winfo_children()[-1]
        results.append(
            capture_tk_window(
                assistant,
                output_dir,
                "desktop-assistant-settings",
                ("Assistant Settings", "Provider", "Model", "Ollama Local"),
            )
        )
        destroy_window(assistant)

        credential_manager = MCPTokenManager(APP_DIR / "mcp_tokens.json")
        visual_credential = credential_manager.create_credential(
            "Visual smoke reader",
            audience="mcp",
            scopes=[MCP_READ_SCOPE],
            expires_in_seconds=2_592_000,
        )
        credential_manager.validate(
            visual_credential.token,
            "list_bookmarks",
        )
        credential_manager.validate(
            visual_credential.token,
            "delete_bookmark",
        )
        app._credential_manager = credential_manager
        root.deiconify()
        root.update()
        _prepare_background_window(root)
        app._show_credential_security()
        credential_dialog = root.winfo_children()[-1]
        _prepare_background_window(credential_dialog)
        credential_dialog.deiconify()
        credential_dialog.update()
        assert_actionable_controls_inside(credential_dialog)
        assert_named_controls_visible(
            credential_dialog,
            ("New credential", "Rotate selected", "Revoke selected", "Close"),
        )
        results.append(
            capture_tk_window(
                credential_dialog,
                output_dir,
                "desktop-access-credentials",
                (
                    "Access Credentials",
                    "Visual smoke reader",
                    "Credential inventory",
                    "Recent credential activity",
                ),
            )
        )
        destroy_window(credential_dialog)

        import_modal = ImportProgressModal(root, source_label="visual-smoke.html")
        import_modal.set_progress(12, 40, 8, 4)
        results.append(
            capture_tk_window(
                import_modal,
                output_dir,
                "desktop-import-progress",
                ("Importing from visual-smoke.html", "Processing bookmark", "added"),
            )
        )
        destroy_window(import_modal)

        import_center = ImportCenterDialog(
            root,
            sources=build_import_sources(("chrome", "firefox")),
            on_select=lambda _source: None,
        )
        apply_screen_aware_geometry(
            import_center, 900, 680, screen_width=1280, screen_height=720,
        )
        import_center.update()
        assert_actionable_controls_inside(import_center)
        results.append(
            capture_tk_window(
                import_center,
                output_dir,
                "desktop-import-center",
                ("Import Center", "Chrome bookmarks", "Files stay on this device"),
            )
        )
        destroy_window(import_center)

        cleanup_dialog = CleanupReviewDialog(
            root,
            title="Duplicate Review",
            intro="Select duplicate groups to remove. A safepoint is created before changes.",
            groups=[
                CleanupReviewGroup(
                    key="visual-duplicate",
                    title="example.com/article",
                    subtitle="1 duplicate bookmark will be removed; earliest item is kept.",
                    items=(
                        "Keep #501: Visual Regression Guide - https://example.com/visual-regression",
                        "Remove #505: Visual Regression Copy - https://example.com/visual-regression?utm_source=x",
                    ),
                    action_label="Remove 1 duplicate",
                ),
                CleanupReviewGroup(
                    key="visual-tags",
                    title="Normalize to 'python'",
                    subtitle="2 bookmarks affected; 1 variant tag.",
                    items=("Merge 'Python' -> 'python'",),
                    action_label="Merge 1 variant",
                ),
            ],
            on_apply=lambda keys: (
                f"Applied {len(keys)} selected group."
                if len(keys) == 1
                else f"Applied {len(keys)} selected groups."
            ),
            on_restore=lambda: True,
        )
        results.append(
            capture_tk_window(
                cleanup_dialog,
                output_dir,
                "desktop-cleanup-review",
                ("Duplicate Review", "Apply selected", "Restore last safepoint", "Remove #505"),
            )
        )
        destroy_window(cleanup_dialog)

        read_later_dialog = ReadLaterQueueDialog(
            root,
            bookmark_manager=app.bookmark_manager,
            on_changed=app._refresh_all,
            on_open_url=lambda _url: True,
        )
        results.append(
            capture_tk_window(
                read_later_dialog,
                output_dir,
                "desktop-read-later-queue",
                ("Read Later Queue", "Open Next", "Mark Done", "Visual Regression Guide"),
            )
        )
        destroy_window(read_later_dialog)

        export_dialog = SelectiveExportDialog(root, app.bookmark_manager)
        results.append(
            capture_tk_window(
                export_dialog,
                output_dir,
                "desktop-export-dialog",
                ("Export Bookmarks", "Choose a format", "Choose categories"),
            )
        )
        destroy_window(export_dialog)

        article_text = (
            "Visual regression checks keep premium desktop surfaces honest. "
            "They catch blank captures, missing labels, and controls that drift "
            "outside their expected frame before release packaging."
        )
        extracted_path = APP_DIR / "extracted" / "visual-smoke-reader.txt"
        extracted_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_path.write_text(article_text, encoding="utf-8")
        reader_bookmark = Bookmark(
            id=504,
            url="https://example.com/reader",
            title="Reader QA Notes",
            category="Research",
            extracted_text_path=str(extracted_path),
        )
        reader_store = ReaderAnnotationStore(APP_DIR / "reader_annotations_visual.json")
        reader_store.add_from_text(504, article_text, 0, 25, color="yellow", note="Visual smoke highlight")
        reader_dialog = ReaderViewDialog(root, reader_bookmark, store=reader_store)
        results.append(
            capture_tk_window(
                reader_dialog,
                output_dir,
                "desktop-reader-view",
                ("Reader QA Notes", "Highlights", "Select text in the reader"),
            )
        )
        destroy_window(reader_dialog)
        reader_dialog = ReaderViewDialog(root, reader_bookmark, store=reader_store)
        reader_dialog.highlight_list.selection_set(0)
        reader_dialog._delete_selected_highlight()
        reader_dialog.update()
        results.append(
            capture_tk_window(
                reader_dialog,
                output_dir,
                "desktop-reader-highlight-deleted",
                ("Reader QA Notes", "Undo", "Highlight deleted"),
            )
        )
        reader_dialog._undo_deleted_highlight()
        if reader_store.get(reader_dialog.highlight_ids[0]) is None:
            raise VisualSmokeError("Reader highlight undo did not restore the deleted record")
        destroy_window(reader_dialog)

        reader_store.add_from_text(
            sample_bookmarks[0].id,
            article_text,
            26,
            66,
            color="green",
            note="Review from the collection workspace",
        )
        highlights_workspace = HighlightsWorkspaceDialog(
            root,
            app.bookmark_manager,
            store=reader_store,
        )
        _prepare_background_window(highlights_workspace)
        assert_actionable_controls_inside(highlights_workspace)
        assert_named_controls_visible(
            highlights_workspace,
            (
                "Highlights workspace",
                "Apply filters",
                "Open source",
                "Export filtered",
                "Delete selected",
            ),
        )
        results.append(
            capture_tk_window(
                highlights_workspace,
                output_dir,
                "desktop-highlights-workspace",
                (
                    "Highlights workspace",
                    "Search saved passages",
                    "Bookmark",
                    "Highlight",
                    "Review",
                    "Export filtered",
                ),
            )
        )
        destroy_window(highlights_workspace)

        organization_rules = OrganizationRulesService(app.bookmark_manager)
        organization_rules.add_rule(
            OrganizationRule(
                name="Visual smoke tagging",
                conditions=({"field": "domain", "operator": "contains", "value": "example.com"},),
                actions=({"action": "add_tag", "value": "visual-qa"},),
            )
        )
        organization_rules_dialog = OrganizationRulesDialog(root, app.bookmark_manager)
        _prepare_background_window(organization_rules_dialog)
        assert_actionable_controls_inside(organization_rules_dialog)
        assert_named_controls_visible(
            organization_rules_dialog,
            ("Organization rules", "New", "Preview", "Apply preview", "Import", "Export"),
        )
        results.append(
            capture_tk_window(
                organization_rules_dialog,
                output_dir,
                "desktop-organization-rules",
                (
                    "Organization rules",
                    "Preview deterministic",
                    "Conditions",
                    "Actions",
                    "Apply preview",
                ),
            )
        )
        destroy_window(organization_rules_dialog)

        changed_article_text = (
            "The source was re-extracted with a replacement introduction. "
            "Saved notes remain available even when their original passage disappears."
        )
        extracted_path.write_text(changed_article_text, encoding="utf-8")
        reader_dialog = ReaderViewDialog(root, reader_bookmark, store=reader_store)
        reader_dialog.highlight_list.selection_set(0)
        reader_dialog._on_highlight_selected()
        _prepare_background_window(reader_dialog)
        assert_named_controls_visible(
            reader_dialog,
            ("Relink orphan to selection", "Delete highlight", "Undo"),
        )
        results.append(
            capture_tk_window(
                reader_dialog,
                output_dir,
                "desktop-reader-orphaned-highlight",
                (
                    "Reader QA Notes",
                    "ORPHAN",
                    "Orphaned highlight",
                    "Relink orphan to selection",
                    "Undo",
                ),
            )
        )
        destroy_window(reader_dialog)

        verify_graph_viewports(root, theme_manager, sample_bookmarks)
        theme_manager.set_theme("github_dark")
        graph_dialog = GraphViewDialog(root, sample_bookmarks)
        _prepare_background_window(graph_dialog)
        assert_graph_labels_visible(graph_dialog)
        assert_named_controls_visible(
            graph_dialog,
            ("Bookmark Graph", "Legend", "Selected", "Arrow keys navigate"),
        )
        assert_widget_inside(graph_dialog, graph_dialog.status, "graph keyboard help")
        results.append(
            capture_tk_window(
                graph_dialog,
                output_dir,
                "desktop-graph-view",
                ("Bookmark Graph", "Legend", "Selected"),
            )
        )
        destroy_window(graph_dialog)
    finally:
        try:
            app._on_close()
        except Exception:
            destroy_window(root)

    return results


def extension_init_script() -> str:
    return """
(() => {
  const config = { apiPort: 8765, apiToken: "visual-token", defaultCategory: "Research" };
  const activeTab = { id: 42, url: "https://example.com/visual-regression", title: "Visual QA Handbook" };
  const storageArea = {
    get(keys, callback) {
      const values = { ...config };
      if (typeof callback === "function") { callback(values); return undefined; }
      return Promise.resolve(values);
    },
    set(values, callback) {
      Object.assign(config, values || {});
      if (typeof callback === "function") callback();
      return Promise.resolve();
    }
  };
  const api = {
    storage: { local: storageArea },
    tabs: {
      query(queryInfo, callback) {
        if (typeof callback === "function") { callback([activeTab]); return undefined; }
        return Promise.resolve([activeTab]);
      },
      onActivated: { addListener() {} }
    },
    scripting: {
      executeScript(details, callback) {
        const result = [{ result: "Selected passage from the active page." }];
        if (typeof callback === "function") { callback(result); return undefined; }
        return Promise.resolve(result);
      }
    },
    readingList: {
      query() {
        return Promise.resolve([{ url: "https://example.com/read-later", title: "Read Later Item", hasBeenRead: false }]);
      }
    },
    runtime: {
      lastError: null,
      getURL(path) { return `http://127.0.0.1:8765/__extension/${path}`; },
      sendMessage(message) {
        if (message && message.type === "bop:get-config") {
          return Promise.resolve({ ok: true, config: { ...config } });
        }
        if (message && message.type === "bop:set-api-token") {
          config.apiToken = String(message.apiToken || "");
          return Promise.resolve({ ok: true });
        }
        return Promise.resolve({ ok: false });
      },
      openOptionsPage(callback) {
        if (typeof callback === "function") callback();
        return Promise.resolve();
      }
    }
  };
  window.chrome = api;
  window.browser = api;
})();
"""


def fulfill_api(route) -> None:
    url = route.request.url
    sample_bookmarks = [
        {
            "id": 501,
            "url": "https://example.com/visual-regression",
            "title": "Visual QA Handbook",
            "category": "Research",
        },
        {
            "id": 502,
            "url": "https://docs.python.org/3/library/tkinter.html",
            "title": "Tkinter Reference",
            "category": "Development",
        },
    ]
    if "/__extension/categories.json" in url:
        payload = ["Research", "Development", "Browsers", "Read Later"]
    elif "/stats" in url:
        payload = {"total_bookmarks": len(sample_bookmarks)}
    elif "/digest" in url:
        payload = {"sections": [{"title": "Rediscover", "bookmarks": sample_bookmarks[:1]}]}
    elif "/search" in url:
        payload = {"results": sample_bookmarks}
    elif "/bookmarks" in url and route.request.method == "POST":
        payload = {"id": 999, "status": "created"}
        route.fulfill(status=201, content_type="application/json", body=json.dumps(payload))
        return
    elif "/bookmarks" in url:
        payload = {"bookmarks": sample_bookmarks}
    else:
        payload = {"name": "Bookmark Organizer Pro", "version": "6.11.0"}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


def check_browser_layout(page, surface: ExtensionSurface) -> None:
    body_text = page.locator("body").inner_text(timeout=5000)
    require_text(surface.name, body_text, surface.expected_text)
    overflow = page.evaluate(
        """() => ({
            scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
            clientWidth: document.documentElement.clientWidth
        })"""
    )
    if overflow["scrollWidth"] > overflow["clientWidth"] + 1:
        raise VisualSmokeError(
            f"{surface.name} has horizontal overflow: {overflow['scrollWidth']} > {overflow['clientWidth']}"
        )
    if surface.html_file == "popup.html":
        hint = page.locator(".choice-group .field-hint").first
        metrics = hint.evaluate(
            """(node) => {
                const style = getComputedStyle(node);
                return {
                    text: node.textContent || '',
                    clientHeight: node.clientHeight,
                    scrollHeight: node.scrollHeight,
                    overflow: style.overflow,
                    textOverflow: style.textOverflow,
                    lineClamp: style.webkitLineClamp,
                };
            }"""
        )
        if metrics["scrollHeight"] > metrics["clientHeight"] + 1:
            raise VisualSmokeError(f"{surface.name} helper text is vertically clipped")
        if metrics["overflow"] == "hidden" or metrics["textOverflow"] == "ellipsis" or metrics["lineClamp"] not in {"none", "normal"}:
            raise VisualSmokeError(f"{surface.name} helper text is still truncated")
        require_text(surface.name, metrics["text"], ("sanitized", "cookies"))


def run_extension_smoke(output_dir: Path) -> list[CaptureResult]:
    from playwright.sync_api import sync_playwright

    results: list[CaptureResult] = []
    errors: list[str] = []
    extension_dir = ROOT / "browser-extension"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for surface in EXTENSION_SURFACES:
                context = browser.new_context(
                    viewport={"width": surface.viewport[0], "height": surface.viewport[1]},
                    color_scheme=surface.color_scheme,
                )
                context.add_init_script(extension_init_script())
                context.route("http://127.0.0.1:8765/**", fulfill_api)
                page = context.new_page()
                page.on("console", lambda message: errors.append(f"{surface.name}: {message.text}") if message.type == "error" else None)
                page.on("pageerror", lambda error: errors.append(f"{surface.name}: {error}"))
                page.goto((extension_dir / surface.html_file).as_uri(), wait_until="domcontentloaded")
                if surface.click_selector:
                    page.locator(surface.click_selector).click()
                page.wait_for_timeout(350)
                check_browser_layout(page, surface)
                output_path = output_dir / f"{surface.name}.png"
                page.screenshot(path=str(output_path), full_page=False)
                width, height = assert_image_healthy(
                    output_path,
                    min_width=min(240, surface.viewport[0]),
                    min_height=min(180, surface.viewport[1]),
                )
                results.append(CaptureResult(surface.name, output_path, width, height))
                context.close()
        finally:
            browser.close()

    if errors:
        raise VisualSmokeError("Extension console/page errors:\n" + "\n".join(errors))
    return results


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    temp_data = None
    if args.data_dir:
        data_dir = args.data_dir.resolve()
    else:
        temp_data = tempfile.TemporaryDirectory(prefix="bop-visual-data-", ignore_cleanup_errors=True)
        data_dir = Path(temp_data.name).resolve()

    watchdog = ScriptWatchdog(
        "visual-smoke",
        total_timeout=args.total_timeout,
        phase_timeout=args.phase_timeout,
        artifact_dir=output_dir,
    )
    try:
        results: list[CaptureResult] = []
        if args.surface in {"all", "desktop"}:
            watchdog.phase("desktop-surfaces")
            results.extend(run_desktop_smoke(output_dir, data_dir))
            watchdog.check("desktop surface capture")
        if args.surface in {"all", "extension"}:
            watchdog.phase("extension-surfaces")
            results.extend(run_extension_smoke(output_dir))
            watchdog.check("extension surface capture")

        summary = {
            "output_dir": str(output_dir),
            "captures": [
                {"name": result.name, "path": str(result.path), "width": result.width, "height": result.height}
                for result in results
            ],
        }
        watchdog.finish()
        print(json.dumps(summary, indent=2))
        return 0
    except VisualSmokeError as exc:
        watchdog.fail(exc)
        print(f"visual smoke failed: {exc}", file=sys.stderr)
        return 1
    except BaseException as exc:
        watchdog.fail(exc)
        print(f"visual smoke failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if temp_data is not None:
            temp_data.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
