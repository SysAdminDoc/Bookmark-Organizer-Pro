import ast
from pathlib import Path
from types import SimpleNamespace

from bookmark_organizer_pro.services.bookmark_graph import BookmarkGraph, GraphNode
from bookmark_organizer_pro.services.settings_store import load_settings
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
    assert report["tk"]["semantic_bookmark_table"] is True


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
    assert load_settings(settings)["theme"] == "Studio Dark"
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


def test_library_table_exposes_keyboard_actions_and_named_columns():
    shell_source = (
        ROOT / "bookmark_organizer_pro/app_mixins/app_shell.py"
    ).read_text(encoding="utf-8")
    for sequence in (
        'self.tree.bind("<Return>"',
        'self.tree.bind("<space>"',
        'self.tree.bind("<Shift-F10>"',
        'self.tree.bind("<KeyPress-Menu>"',
    ):
        assert sequence in shell_source
    assert 'self.tree.heading("#0", text=_("Site"))' in shell_source
    assert 'self.tree.heading("favorite", text=_("Pinned"))' in shell_source


def test_highlights_workspace_exposes_keyboard_actions_and_bounded_source_loading():
    workspace_source = (
        ROOT / "bookmark_organizer_pro/ui/highlights_workspace.py"
    ).read_text(encoding="utf-8")
    for sequence in (
        'self.bind("<Escape>"',
        'self.bind("<Return>"',
        'self.bind("<Delete>"',
        'self.tree.bind("<Double-1>"',
    ):
        assert sequence in workspace_source
    assert 'selectmode="extended"' in workspace_source
    assert "highlight_id=item.id" in workspace_source
    assert "read_extracted_text" not in workspace_source


def test_organization_rules_workspace_exposes_preview_and_keyboard_actions():
    workspace_source = (
        ROOT / "bookmark_organizer_pro/ui/organization_rules.py"
    ).read_text(encoding="utf-8")
    for sequence in (
        'self.bind("<Escape>"',
        'self.bind("<Return>"',
        'self.bind("<Delete>"',
        'text=_("Preview")',
        'text=_("Apply preview")',
    ):
        assert sequence in workspace_source
    assert "OrganizationRulesService" in workspace_source
    assert "OrganizationRuleEditorDialog" in workspace_source


# ── R-184: the modal dialog keyboard contract ────────────────────────────────
#
# A Toplevel that calls grab_set() takes the pointer and the keyboard. Every one
# of them must also be dismissible and reachable from the keyboard alone, or a
# keyboard user can open it and be stuck. The convention was followed by most
# dialogs and enforced by nothing, so the Trash workspace shipped without it.

MODAL_SOURCE_DIRS = ("ui", "app_mixins")
MODAL_REQUIREMENTS = {
    "transient": "call transient(parent) so the dialog stays with its owner",
    "escape": "bind <Escape> to the cancel or close path",
    "focus": "place initial focus inside the dialog",
}
# WM_DELETE_WINDOW is deliberately not required. Tk already destroys a
# Toplevel when its close button is used, so demanding a handler everywhere
# would add inert boilerplate to every dialog. What matters is that a dialog
# which DOES guard its close does not let Escape walk around the guard, which
# test_escape_routes_through_an_existing_close_guard checks instead.


def _enclosing_scopes(tree: ast.AST) -> dict:
    """Map every node to the INNERMOST function or class body enclosing it.

    ast.walk is breadth-first, so a class is visited before its methods. Keeping
    the first scope seen would make the class own every method's nodes, and one
    method's focus call would then vouch for a different method's dialog.
    Overwriting instead lets the deeper scope win.
    """
    owner = {}
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for child in ast.walk(scope):
            owner[child] = scope
    return owner


def _scope_parents(tree: ast.AST) -> dict:
    """Map each scope to the scope directly containing it."""
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _creates_window(scope, receiver: str, parents: dict) -> bool:
    """Whether this scope is the one that brings the modal window into being.

    A grab_set on a window created elsewhere is a re-grab, not a new modal:
    ui/about.py restores its own grab after closing a child preview, and it
    should not be asked to re-declare a contract it already satisfies where the
    window is built.
    """
    for child in ast.walk(scope):
        if isinstance(child, ast.Assign) and isinstance(child.value, ast.Call):
            try:
                factory = ast.unparse(child.value.func)
            except Exception:
                continue
            if not factory.endswith("Toplevel"):
                continue
            for target in child.targets:
                try:
                    if ast.unparse(target) == receiver:
                        return True
                except Exception:
                    continue
    if receiver != "self":
        return False
    owner = parents.get(scope)
    if not isinstance(owner, ast.ClassDef):
        return False
    return any("Toplevel" in ast.unparse(base) for base in owner.bases)


def _modal_targets(tree: ast.AST):
    """Yield (scope, receiver) for every grab_set() call in a module.

    Keyed on the receiver rather than the enclosing class, because a class whose
    other methods happen to call focus_set would otherwise satisfy the contract
    on behalf of a sibling dialog that does not. Keyed on the node itself rather
    than a scope name, because two scopes can share a name.
    """
    owner = _enclosing_scopes(tree)
    parents = _scope_parents(tree)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "grab_set":
            continue
        receiver = ast.unparse(node.func.value)
        scope = owner.get(node)
        if scope is None or not _creates_window(scope, receiver, parents):
            continue
        yield scope, receiver


def _receiver_calls(scope, receiver: str) -> set:
    """Method names called on `receiver` anywhere in `scope`."""
    names = set()
    for child in ast.walk(scope):
        if not (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)):
            continue
        try:
            if ast.unparse(child.func.value) == receiver:
                names.add(child.func.attr)
        except Exception:
            continue
    return names


def _receiver_bindings(scope, receiver: str) -> set:
    """String literals passed to `receiver.bind(...)` or `.protocol(...)`."""
    literals = set()
    for child in ast.walk(scope):
        if not (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)):
            continue
        if child.func.attr not in {"bind", "protocol"}:
            continue
        try:
            if ast.unparse(child.func.value) != receiver:
                continue
        except Exception:
            continue
        for argument in child.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                literals.add(argument.value)
    return literals


def _scope_places_focus(scope) -> bool:
    """Whether anything in this scope puts keyboard focus inside the dialog."""
    for child in ast.walk(scope):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr in {"focus_set", "focus_force"}
        ):
            return True
    return False


def _modal_contract_violations(root: Path) -> list:
    violations = []
    for directory in MODAL_SOURCE_DIRS:
        source_root = root / "bookmark_organizer_pro" / directory
        if not source_root.is_dir():
            continue
        for source in sorted(source_root.rglob("*.py")):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for scope, receiver in _modal_targets(tree):
                if scope is None:
                    continue
                calls = _receiver_calls(scope, receiver)
                bindings = _receiver_bindings(scope, receiver)
                missing = set()
                if "transient" not in calls:
                    missing.add("transient")
                if "<Escape>" not in bindings:
                    missing.add("escape")
                # Focus may land on any widget inside the dialog, and focusing
                # the first field is better than focusing the window, so this
                # one is checked across the scope rather than on the receiver.
                if not _scope_places_focus(scope):
                    missing.add("focus")
                if missing:
                    relative = source.relative_to(root).as_posix()
                    violations.append((relative, f"{scope.name}:{receiver}", sorted(missing)))
    return violations


def test_every_modal_dialog_can_be_dismissed_from_the_keyboard():
    violations = _modal_contract_violations(Path(__file__).resolve().parents[1])

    assert not violations, "\n".join(
        f"{path}:{scope} is modal but does not "
        + "; ".join(MODAL_REQUIREMENTS[name] for name in missing)
        for path, scope, missing in violations
    )


def test_escape_routes_through_an_existing_close_guard():
    """A guarded close must not be bypassable with a keystroke.

    live_workflow asks a running job to cancel rather than tearing the window
    down, so its Escape has to reach the same handler its close button does.
    """
    source = (
        Path(__file__).resolve().parents[1]
        / "bookmark_organizer_pro" / "ui" / "live_workflow.py"
    ).read_text(encoding="utf-8")

    assert 'dialog.protocol("WM_DELETE_WINDOW", self._on_close_request)' in source
    assert 'dialog.bind("<Escape>", lambda _event: self._on_close_request())' in source


def test_the_modal_contract_gate_reports_a_dialog_that_breaks_it(tmp_path: Path):
    """Prove the gate fails, so a green run means something."""
    package = tmp_path / "bookmark_organizer_pro" / "ui"
    package.mkdir(parents=True)
    (tmp_path / "bookmark_organizer_pro" / "app_mixins").mkdir(parents=True)
    (package / "leaky.py").write_text(
        "import tkinter as tk\n"
        "\n"
        "def show(parent):\n"
        "    dialog = tk.Toplevel(parent)\n"
        "    dialog.transient(parent)\n"
        "    dialog.grab_set()\n"
        "    dialog.focus_set()\n"
        "    dialog.protocol('WM_DELETE_WINDOW', dialog.destroy)\n",
        encoding="utf-8",
    )

    violations = _modal_contract_violations(tmp_path)

    assert violations == [
        ("bookmark_organizer_pro/ui/leaky.py", "show:dialog", ["escape"])
    ]


def test_the_gate_is_not_fooled_by_a_sibling_that_meets_the_contract(tmp_path: Path):
    """A compliant dialog must not vouch for a non-compliant one.

    Keying on the enclosing class let any method's focus_set satisfy every
    modal in that class, and keying on the scope NAME let a compliant method
    silence a module-level function that happened to share its name.
    """
    package = tmp_path / "bookmark_organizer_pro" / "ui"
    package.mkdir(parents=True)
    (tmp_path / "bookmark_organizer_pro" / "app_mixins").mkdir(parents=True)
    (package / "collide.py").write_text(
        "\n".join([
            "import tkinter as tk",
            "",
            "class Good(tk.Toplevel):",
            "    def show(self):",
            "        self.transient(self.master)",
            "        self.grab_set()",
            "        self.focus_set()",
            "        self.bind('<Escape>', lambda e: self.destroy())",
            "",
            "def show(parent):",
            "    dialog = tk.Toplevel(parent)",
            "    dialog.grab_set()",
            "",
        ]),
        encoding="utf-8",
    )

    violations = _modal_contract_violations(tmp_path)

    assert violations == [
        (
            "bookmark_organizer_pro/ui/collide.py",
            "show:dialog",
            ["escape", "focus", "transient"],
        )
    ]
