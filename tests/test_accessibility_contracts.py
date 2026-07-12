from pathlib import Path
from types import SimpleNamespace

from bookmark_organizer_pro.services.bookmark_graph import BookmarkGraph, GraphNode
from bookmark_organizer_pro.ui.components import ScrollableFrame
from bookmark_organizer_pro.ui.graph_view import GraphViewDialog, _directional_node_id
from bookmark_organizer_pro.ui import treeview
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


class _FakeCanvas:
    def __init__(self):
        self.bound = []
        self.unbound = []
        self.scrolls = []

    def bind_all(self, sequence, callback):
        self.bound.append((sequence, callback))

    def unbind_all(self, sequence):
        self.unbound.append(sequence)

    def yview_scroll(self, units, mode):
        self.scrolls.append((units, mode))


def test_scrollable_frame_binds_cross_platform_wheel_events():
    frame = object.__new__(ScrollableFrame)
    frame.canvas = _FakeCanvas()

    frame._activate_mousewheel()
    assert [sequence for sequence, _callback in frame.canvas.bound] == [
        "<MouseWheel>", "<Button-4>", "<Button-5>"
    ]
    frame._unbind_mousewheel_events()
    assert frame.canvas.unbound == ["<MouseWheel>", "<Button-4>", "<Button-5>"]


def test_scrollable_frame_handles_linux_buttons_and_small_macos_deltas():
    frame = object.__new__(ScrollableFrame)
    frame.canvas = _FakeCanvas()

    for event in (
        SimpleNamespace(num=4, delta=0),
        SimpleNamespace(num=5, delta=0),
        SimpleNamespace(num=None, delta=1),
        SimpleNamespace(num=None, delta=-1),
    ):
        assert frame._on_mousewheel(event) == "break"

    assert frame.canvas.scrolls == [
        (-1, "units"),
        (1, "units"),
        (-1, "units"),
        (1, "units"),
    ]


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
