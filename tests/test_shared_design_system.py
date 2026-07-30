"""Focused contracts for the desktop design-system state vocabulary."""

from __future__ import annotations

from types import SimpleNamespace

from bookmark_organizer_pro.ui import shell_widgets, treeview, widget_controls
from bookmark_organizer_pro.ui.foundation import DesignTokens, FONTS
from bookmark_organizer_pro.ui.style_manager import StyleManager
from bookmark_organizer_pro.ui.theme import ThemeColors
from bookmark_organizer_pro.ui.workflow_detail_panel import (
    BookmarkDetailPanel,
    _bookmark_type,
    _format_date,
    _next_action,
)
from bookmark_organizer_pro.app_mixins.app_shell import AppShellMixin
from bookmark_organizer_pro.app_mixins.bookmarks import (
    _bookmark_status,
    _relative_added,
    _saved_cell,
)
from bookmark_organizer_pro.models import Bookmark
from datetime import datetime


class _RecordingStyle:
    def __init__(self):
        self.configurations = {}
        self.maps = {}

    def configure(self, name, **kwargs):
        self.configurations[name] = kwargs

    def map(self, name, **kwargs):
        self.maps[name] = kwargs


class _Configurable:
    def __init__(self):
        self.options = {}

    def configure(self, **kwargs):
        self.options.update(kwargs)


def test_desktop_scale_matches_dense_library_workspace():
    assert (DesignTokens.SPACE_XS, DesignTokens.SPACE_SM) == (4, 8)
    assert DesignTokens.RADIUS_LG <= 8
    assert DesignTokens.TREEVIEW_ROW_HEIGHT == 64
    assert DesignTokens.TABLE_HEADER_HEIGHT == 40
    assert DesignTokens.RIGHT_SIDEBAR_WIDTH == 336
    assert FONTS.size_display < 28
    assert DesignTokens.BUTTON_PAD_Y == DesignTokens.CONTROL_GAP


def test_ttk_controls_define_complete_interaction_states(monkeypatch):
    colors = ThemeColors()
    style = _RecordingStyle()
    manager = object.__new__(StyleManager)
    manager.style = style
    manager._current_theme_colors = None
    monkeypatch.setattr(manager, "_apply_platform_base_theme", lambda _colors: None)

    manager.apply_theme(colors)

    assert style.configurations["Treeview"]["rowheight"] == 64
    assert ("active", colors.bg_hover) in style.maps["Treeview"]["background"]
    assert ("disabled", colors.bg_tertiary) in style.maps["Treeview"]["background"]
    assert ("focus", colors.border_active) in style.maps["Treeview"]["bordercolor"]
    for style_name in ("TButton", "Primary.TButton", "Toolbar.TButton"):
        assert "disabled" in {state for state, _value in style.maps[style_name]["foreground"]}
    assert ("focus", colors.border_active) in style.maps["TEntry"]["bordercolor"]
    assert ("disabled", colors.bg_tertiary) in style.maps["TCombobox"]["fieldbackground"]


def test_modern_button_focus_and_press_are_distinct_states(monkeypatch):
    colors = ThemeColors()
    monkeypatch.setattr(widget_controls, "get_theme", lambda: colors)
    button = object.__new__(widget_controls.ModernButton)
    button.state = "normal"
    button._is_hovered = False
    button._is_focused = False
    button._is_pressed = False
    button._normal_border = colors.border_muted
    button._pressed_bg = colors.selection
    button.default_bg = colors.bg_secondary
    button.hover_bg = colors.bg_hover
    button.fg = colors.text_primary
    button.hover_fg = colors.text_primary
    button.label = _Configurable()
    button.options = {}
    button.command = None
    button.configure = lambda **kwargs: button.options.update(kwargs)

    button._on_focus_in(None)
    assert button.options["highlightthickness"] == DesignTokens.FOCUS_RING_WIDTH
    assert button.options["highlightbackground"] == colors.accent_primary
    button._on_press(None)
    assert button._is_pressed is True
    assert button.options["bg"] == colors.selection
    button._on_focus_out(None)
    assert button.options["highlightthickness"] == DesignTokens.BORDER_WIDTH


class _HoverSheet:
    def __init__(self):
        self.highlighted = []
        self.redraws = 0

    def identify_row(self, _event, **_kwargs):
        return 1

    def highlight_rows(self, row, **kwargs):
        self.highlighted.append((row, kwargs))

    def redraw(self):
        self.redraws += 1


def test_virtual_table_hover_is_quiet_and_row_scoped(monkeypatch):
    colors = ThemeColors()
    monkeypatch.setattr(
        "bookmark_organizer_pro.ui.widget_runtime.get_theme",
        lambda: colors,
    )
    table = object.__new__(treeview.VirtualBookmarkSheet)
    table._sheet = _HoverSheet()
    table._row_to_id = ["one", "two"]
    table._hovered_row = None
    restored = []
    table._apply_row_highlights = lambda redraw=True: restored.append(redraw)

    table._on_table_motion(SimpleNamespace())

    assert table._hovered_row == 1
    assert restored == [False]
    assert table._sheet.highlighted[0][0] == 1
    assert table._sheet.highlighted[0][1]["bg"] == colors.bg_hover


def test_dropdown_keyboard_selection_wraps(monkeypatch):
    monkeypatch.setattr(shell_widgets, "get_theme", lambda: ThemeColors())
    menu = object.__new__(shell_widgets.StyledDropdownMenu)
    menu._menu_items = [(_Configurable(), lambda: None), (_Configurable(), lambda: None)]
    menu._selected_index = 0

    assert menu._move_selection(-1) == "break"
    assert menu._selected_index == 1
    assert menu._move_selection(1) == "break"
    assert menu._selected_index == 0


def test_library_rows_surface_time_and_state_without_color_only():
    now = datetime(2026, 7, 12, 12, 0)
    assert _relative_added("2026-07-12T08:00:00", now) == "Today"
    assert _relative_added("2026-07-11T08:00:00", now) == "Yesterday"
    assert _relative_added("2026-07-09T08:00:00", now) == "3 days ago"
    assert _relative_added("not-a-date", now) == "—"
    assert _saved_cell("2026-07-12T08:00:00", now) == "Today\nJul 12"
    assert _saved_cell("2026-06-12T08:00:00", now) == "Jun 12\n2026"

    bookmark = Bookmark(id=1, url="https://example.com", title="Example")
    assert _bookmark_status(bookmark) == "● Unread"
    bookmark.visit_count = 1
    assert _bookmark_status(bookmark) == "● Read"
    bookmark.read_later = True
    assert _bookmark_status(bookmark) == "● Read later"
    bookmark.is_valid = False
    assert _bookmark_status(bookmark) == "● Needs review"


def test_contextual_inspector_formats_type_time_and_offline_state(tmp_path):
    assert _bookmark_type("https://example.com/reference.pdf") == "PDF"
    assert _bookmark_type("https://example.com/watch.webm") == "Video"
    assert _bookmark_type("https://example.com/article") == "Website"
    assert _format_date("2026-07-14T08:05:00").startswith("Jul 14, 2026")
    assert _format_date("not-a-date") == "not-a-date"

    bookmark = Bookmark(id=2, url="https://example.com", title="Example")
    assert BookmarkDetailPanel._offline_state(bookmark) == "Not captured"
    snapshot = tmp_path / "snapshot.html"
    snapshot.write_bytes(b"x" * 2048)
    bookmark.snapshot_path = str(snapshot)
    assert BookmarkDetailPanel._offline_state(bookmark) == "Available (2 KB)"
    bookmark.snapshot_mime_type = "application/pdf"
    assert BookmarkDetailPanel._offline_state(bookmark) == "Available (PDF, 2 KB)"


def test_contextual_inspector_recommends_one_state_aware_next_action():
    bookmark = Bookmark(
        id=3,
        url="https://example.com",
        title="Example",
        read_later=True,
    )
    assert _next_action(bookmark)[2:] == ("Continue reading", "open")
    bookmark.read_later = False
    assert _next_action(bookmark)[2:] == ("Add a note", "edit")
    bookmark.is_valid = False
    assert _next_action(bookmark)[2:] == ("Review details", "edit")


def test_single_selection_opens_contextual_focus_inspector():
    bookmark = Bookmark(id=3, url="https://example.com", title="Example", visit_count=1)

    class Manager:
        def get_bookmark(self, bookmark_id):
            return bookmark if bookmark_id == bookmark.id else None

    class Inspector:
        def __init__(self):
            self.calls = []

        def show_bookmark(self, selected, **context):
            self.calls.append((selected, context))

        def clear(self, _message=None):
            raise AssertionError("single selection should not clear the inspector")

    shell = object.__new__(AppShellMixin)
    shell.bookmark_manager = Manager()
    shell.bookmark_inspector = Inspector()
    shell.selected_bookmarks = [bookmark.id]
    shell.root = SimpleNamespace(winfo_width=lambda: 1540)
    shell._right_rail_user_hidden = False
    visibility = []
    modes = []
    shell._apply_right_rail_visibility = visibility.append
    shell._set_right_rail_mode = modes.append

    shell._update_right_rail_selection()

    selected, context = shell.bookmark_inspector.calls[0]
    assert selected is bookmark
    assert context == {}
    assert visibility == [True]
    assert modes == ["focus"]


def test_favorite_column_release_routes_to_direct_pin_action():
    class Tree:
        @staticmethod
        def column_at_event(_event):
            return "favorite"

        @staticmethod
        def identify_row(_event):
            return "42"

    class Root:
        @staticmethod
        def after_idle(callback):
            callback()

    shell = object.__new__(AppShellMixin)
    shell.tree = Tree()
    shell.root = Root()
    toggled = []
    shell._toggle_pin_from_row = toggled.append

    assert shell._on_library_table_release(SimpleNamespace()) == "break"
    assert toggled == ["42"]
