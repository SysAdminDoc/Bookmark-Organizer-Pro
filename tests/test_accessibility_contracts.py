from pathlib import Path
from types import SimpleNamespace

from bookmark_organizer_pro.services.bookmark_graph import BookmarkGraph, GraphNode
from bookmark_organizer_pro.ui.graph_view import GraphViewDialog, _directional_node_id
from bookmark_organizer_pro.ui import treeview
from bookmark_organizer_pro.ui.tk_interactions import (
    ScopedMousewheelBinding,
    WHEEL_EVENTS,
    wheel_scroll_units,
)
from scripts import accessibility_contract_smoke as a11y


ROOT = Path(__file__).resolve().parents[1]


def test_extension_accessibility_contracts_cover_all_extension_pages():
    report = a11y.run_checks()

    checked = {entry["file"] for entry in report["extension"]}
    assert checked == {"popup.html", "options.html", "sidepanel.html"}
    assert report["tk"]["focusable_label"] is True
    assert report["tk"]["modern_button"] is True
    assert report["tk"]["native_bookmark_table"] is True


def test_accessibility_contract_rejects_unlabelled_controls(tmp_path: Path):
    page = tmp_path / "bad.html"
    page.write_text(
        """<!doctype html>
<html lang="en">
<head><title>Bad</title></head>
<body><main><input id="missing"></main></body>
</html>
""",
        encoding="utf-8",
    )

    try:
        a11y.check_extension_file(page)
    except a11y.AccessibilityContractError as exc:
        assert "accessible name" in str(exc)
    else:
        raise AssertionError("unlabelled control should fail accessibility contract")


def test_graph_directional_navigation_prefers_aligned_nearest_node():
    nodes = [
        GraphNode("center", "Center", "bookmark", x=50, y=50),
        GraphNode("right-near", "Right", "tag", x=80, y=52),
        GraphNode("right-diagonal", "Diagonal", "tag", x=70, y=90),
        GraphNode("left", "Left", "tag", x=10, y=50),
    ]

    assert _directional_node_id(nodes, "center", "Right") == "right-near"
    assert _directional_node_id(nodes, "center", "Left") == "left"
    assert _directional_node_id(nodes, None, "Right") == "center"


def test_graph_tab_navigation_wraps_without_tk_window():
    dialog = object.__new__(GraphViewDialog)
    dialog.graph = BookmarkGraph(
        nodes=[
            GraphNode("one", "One", "bookmark"),
            GraphNode("two", "Two", "tag"),
        ],
        edges=[],
    )
    dialog.selected_node_id = None
    selected = []
    dialog._select_node = selected.append

    assert dialog._on_tab_navigation(SimpleNamespace(state=0)) == "break"
    assert selected[-1] == "one"
    dialog.selected_node_id = "one"
    assert dialog._on_tab_navigation(SimpleNamespace(state=0x0001)) == "break"
    assert selected[-1] == "two"


def test_graph_keyboard_activation_opens_selected_bookmark():
    bookmark = object()
    opened = []
    dialog = object.__new__(GraphViewDialog)
    dialog.selected_node_id = "bookmark:42"
    dialog.bookmarks_by_node = {"bookmark:42": bookmark}
    dialog.on_open_bookmark = opened.append

    assert dialog._on_keyboard_activate() == "break"
    assert opened == [bookmark]


class _FakeTarget:
    def __init__(self):
        self.bound = []
        self.unbound = []

    def bind(self, sequence, callback, add=None):
        self.bound.append((sequence, callback))
        return f"binding-{len(self.bound)}"

    def unbind(self, sequence, binding_id):
        self.unbound.append((sequence, binding_id))


class _FakeHost:
    def __init__(self, target):
        self.target = target
        self.bound = []
        self.pointer_widget = self

    def winfo_toplevel(self):
        return self.target

    def bind(self, sequence, callback, add=None):
        self.bound.append((sequence, callback))

    def winfo_pointerxy(self):
        return (10, 20)

    def winfo_containing(self, _x, _y):
        return self.pointer_widget


def test_scoped_wheel_binding_is_cross_platform_and_targeted():
    target = _FakeTarget()
    host = _FakeHost(target)
    scrolls = []
    binding = ScopedMousewheelBinding(host, lambda units, event: scrolls.append((units, event)))

    assert [sequence for sequence, _callback in target.bound] == list(WHEEL_EVENTS)
    event = SimpleNamespace(num=4, delta=0)
    assert binding._dispatch(event) == "break"
    assert scrolls == [(-1, event)]

    host.pointer_widget = SimpleNamespace(master=None)
    assert binding._dispatch(SimpleNamespace(num=5, delta=0)) is None
    binding.close()
    assert target.unbound == [
        ("<MouseWheel>", "binding-1"),
        ("<Button-4>", "binding-2"),
        ("<Button-5>", "binding-3"),
    ]


def test_wheel_normalization_handles_linux_buttons_and_small_macos_deltas():
    assert [
        wheel_scroll_units(SimpleNamespace(num=4, delta=0)),
        wheel_scroll_units(SimpleNamespace(num=5, delta=0)),
        wheel_scroll_units(SimpleNamespace(num=None, delta=1)),
        wheel_scroll_units(SimpleNamespace(num=None, delta=-1)),
    ] == [-1, 1, -1, 1]


def test_pointer_and_wheel_contracts_enumerate_custom_surfaces():
    click_surfaces = (
        "bookmark_organizer_pro/app_mixins/app_shell.py",
        "bookmark_organizer_pro/app_mixins/categories.py",
        "bookmark_organizer_pro/app_mixins/dashboard.py",
        "bookmark_organizer_pro/ui/feedback.py",
        "bookmark_organizer_pro/ui/shell_widgets.py",
        "bookmark_organizer_pro/ui/widget_chat_panel.py",
        "bookmark_organizer_pro/ui/workflow_emoji_picker.py",
        "bookmark_organizer_pro/launcher.py",
    )
    for relative in click_surfaces:
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert 'bind("<Button-1>"' not in source, relative
        assert "make_keyboard_activatable" in source, relative

    wheel_surfaces = (
        "bookmark_organizer_pro/ui/components.py",
        "bookmark_organizer_pro/ui/widget_chat_panel.py",
        "bookmark_organizer_pro/ui/widget_bookmark_editor.py",
        "bookmark_organizer_pro/ui/management_dialogs.py",
        "bookmark_organizer_pro/ui/cleanup_review.py",
        "bookmark_organizer_pro/ui/import_center.py",
        "bookmark_organizer_pro/ui/widget_theme_dialogs.py",
        "bookmark_organizer_pro/ui/workflow_emoji_picker.py",
    )
    for relative in wheel_surfaces:
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "bind_scoped_mousewheel" in source, relative
        assert ".bind_all(" not in source, relative
        assert ".unbind_all(" not in source, relative

    chat_source = (ROOT / "bookmark_organizer_pro/ui/widget_chat_panel.py").read_text(encoding="utf-8")
    read_later_source = (ROOT / "bookmark_organizer_pro/ui/read_later_queue.py").read_text(encoding="utf-8")
    assert "Open cited bookmark" in chat_source
    assert 'self.listbox.bind("<space>"' in read_later_source


def test_accessible_bookmark_list_preference_is_persistent_and_non_destructive(tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.write_text('{"theme": "Studio Dark"}', encoding="utf-8")

    treeview.save_accessible_list_mode(True, settings)

    assert treeview.accessible_list_mode_enabled(settings) is True
    assert '"theme": "Studio Dark"' in settings.read_text(encoding="utf-8")
    treeview.save_accessible_list_mode(False, settings)
    assert treeview.accessible_list_mode_enabled(settings) is False


def test_accessible_mode_selects_native_semantic_treeview(monkeypatch):
    calls = []

    def fake_tree(parent, columns, **kwargs):
        calls.append((parent, tuple(columns), kwargs))
        return "native-tree"

    monkeypatch.setattr(treeview, "SortableTreeview", fake_tree)
    result = treeview.BookmarkListWidget(
        "parent", columns=("title", "url"), accessible_mode=True, show="headings"
    )

    assert result == "native-tree"
    assert calls == [("parent", ("title", "url"), {"show": "headings"})]
