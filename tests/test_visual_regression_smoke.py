import inspect
from pathlib import Path
import threading
import types
from unittest import mock
import unittest

from PIL import Image

from scripts import visual_regression_smoke as smoke


def test_visual_smoke_fails_on_background_thread_exception(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    def failing_desktop_smoke(_output_dir, _data_dir):
        def fail():
            raise RuntimeError("worker failed")

        worker = threading.Thread(target=fail, name="visual-worker")
        worker.start()
        worker.join()
        return []

    monkeypatch.setattr(smoke, "run_desktop_smoke", failing_desktop_smoke)

    result = smoke.main(
        [
            "--surface",
            "desktop",
            "--output",
            str(tmp_path / "captures"),
        ]
    )

    assert result == 1
    assert "visual-worker: RuntimeError: worker failed" in capsys.readouterr().err


def test_visual_smoke_surface_matrix_covers_required_desktop_and_extension_views():
    assert {
        "desktop-main-empty-dark",
        "desktop-main-list-dark",
        "desktop-search-error-dark",
        "desktop-main-list-light",
        "desktop-bookmark-editor-1280x720",
        "desktop-about-1280x720",
        "desktop-support-bundle-preview",
        "desktop-dependency-repair-1280x720",
        "desktop-assistant-settings",
        "desktop-import-progress",
        "desktop-import-center",
        "desktop-cleanup-review",
        "desktop-read-later-queue",
        "desktop-trash-workspace-1280x720",
        "desktop-snapshot-failures-sidebar",
        "desktop-export-dialog",
        "desktop-reader-view",
        "desktop-reader-highlight-deleted",
        "desktop-reader-orphaned-highlight",
        "desktop-graph-view",
    } <= set(smoke.DESKTOP_SURFACES)

    extension_names = {surface.name for surface in smoke.EXTENSION_SURFACES}
    assert {
        "extension-popup-dark",
        "extension-popup-light",
        "extension-options-light",
        "extension-sidepanel-recent-dark",
        "extension-sidepanel-add-light",
    } <= extension_names


def test_visual_smoke_rejects_blank_images(tmp_path: Path):
    blank = tmp_path / "blank.png"
    Image.new("RGB", (320, 240), "#111111").save(blank)

    try:
        smoke.assert_image_healthy(blank)
    except smoke.VisualSmokeError as exc:
        assert "blank" in str(exc)
    else:
        raise AssertionError("blank screenshot should fail visual smoke")


def test_background_capture_position_is_outside_virtual_desktop():
    desktop = (-1920, 0, 3840, 1080)
    x, y = smoke._background_position(desktop, 1500, 950)
    assert x + 1500 < desktop[0]
    assert desktop[1] <= y <= desktop[1] + desktop[3]


def test_tk_capture_path_never_requests_foreground_activation():
    source = inspect.getsource(smoke.capture_tk_window)
    assert "focus_force" not in source
    assert ".lift(" not in source
    assert '"-topmost", True' not in source


def test_support_bundle_preview_requires_visible_save_controls():
    source = inspect.getsource(smoke.run_desktop_smoke)
    assert 'assert_named_controls_visible(support_preview, ("Save Bundle", "Cancel"))' in source


def test_windows_capture_resolves_top_level_hwnd_contract():
    source = inspect.getsource(smoke._get_toplevel_hwnd)
    assert "GetAncestor" in source
    assert "winfo_id" in source


def test_desktop_gate_walks_the_tab_ring_not_just_single_controls():
    """R-149. The accessibility contract checks controls one at a time, which a
    control can pass while still being unreachable, because Tab follows a ring
    that does not cross between toplevels. Verified live against the real main
    window: a button parented onto a stray Toplevel is reported, and the
    unmodified window is fully reachable.

    There is deliberately no assertion about traversal order. A first attempt
    scored the ring against reading order across the whole window and flagged
    the real one, which runs search, toolbar, sidebar, content, right rail.
    That order is correct for a multi-pane window, so the check was measuring
    the wrong thing, and loosening it until it passed would have left a gate
    asserting nothing.
    """
    source = inspect.getsource(smoke.assert_keyboard_traversal_reaches_every_control)
    assert "winfo_toplevel()" in source
    assert "Tab never reaches" in source
    assert "a separate toplevel" in source

    ring = inspect.getsource(smoke._tab_ring)
    assert "tk_focusNext" in ring
    assert "did not return to its starting point" in ring

    picker = inspect.getsource(smoke.focusable_widgets)
    assert "winfo_ismapped" in picker
    assert "takefocus" in picker

    desktop = inspect.getsource(smoke.verify_desktop_viewports)
    assert "assert_keyboard_traversal_reaches_every_control(root)" in desktop


def test_desktop_viewport_gate_covers_supported_sizes_and_themes():
    source = inspect.getsource(smoke.verify_desktop_viewports)
    assert smoke.DESKTOP_VIEWPORTS == (
        (1280, 720, 1.0),
        (1540, 980, 1.25),
        (1920, 1080, 1.0),
    )
    # The theme list is a module constant so the palette-contrast suite and the
    # smoke agree on what is covered; assert the coverage itself rather than
    # where the literal happens to live.
    assert smoke.DESKTOP_SMOKE_THEMES == (
        "github_dark",
        "github_light",
        "solarized_dark",
    )
    assert "DESKTOP_SMOKE_THEMES" in source

    # R-137: the nine themes outside the deep matrix are still rendered once
    # each, so a palette that only breaks layout in, say, Nord cannot ship
    # unseen. Together the two lists have to cover every built-in theme.
    from bookmark_organizer_pro.theme_runtime import BUILT_IN_THEMES

    covered = set(smoke.DESKTOP_SMOKE_THEMES) | set(smoke.theme_sweep_names())
    assert covered == set(BUILT_IN_THEMES)
    assert not set(smoke.DESKTOP_SMOKE_THEMES) & set(smoke.theme_sweep_names())
    assert smoke.THEME_SWEEP_VIEWPORT in smoke.DESKTOP_VIEWPORTS
    assert "theme_sweep_names()" in source
    viewport_source = inspect.getsource(smoke._verify_viewport)
    assert "assert_realized_viewport" in viewport_source
    assert "assert_actionable_controls_inside" in viewport_source
    assert "assert_no_horizontal_overflow" in viewport_source
    assert "right rail did not collapse" in source


def test_graph_view_uses_shared_geometry_and_full_viewport_matrix():
    root = Path(__file__).resolve().parents[1]
    graph_source = (root / "bookmark_organizer_pro" / "ui" / "graph_view.py").read_text(encoding="utf-8")
    smoke_source = inspect.getsource(smoke.verify_graph_viewports)

    assert "apply_screen_aware_geometry(self, 1120, 760)" in graph_source
    assert "DESKTOP_VIEWPORTS" in smoke_source
    assert '"github_dark"' in smoke_source
    assert '"github_light"' in smoke_source
    assert "_verify_viewport" in smoke_source


def test_visual_smoke_asserts_graph_dialog_geometry_and_label_collisions():
    root = Path(__file__).resolve().parents[1]
    graph_source = (root / "bookmark_organizer_pro/ui/graph_view.py").read_text(encoding="utf-8")
    smoke_source = inspect.getsource(smoke.run_desktop_smoke)
    graph_smoke_source = inspect.getsource(smoke.assert_graph_labels_visible)
    dialog_smoke_source = inspect.getsource(smoke.verify_dialog_viewports)

    assert "_on_canvas_configure" in graph_source
    assert "_graph_label_text" in graph_source
    assert "_GRAPH_LABEL_OFFSETS" in graph_source
    assert "assert_graph_labels_visible" in smoke_source
    assert "graph labels overlap" in graph_smoke_source
    assert "DESKTOP_VIEWPORTS" in dialog_smoke_source
    assert '"github_dark", "github_light"' in dialog_smoke_source


def test_visual_smoke_asserts_dialog_footers_theme_tokens_and_popup_helper():
    root = Path(__file__).resolve().parents[1]
    editor_source = (root / "bookmark_organizer_pro/ui/widget_bookmark_editor.py").read_text(encoding="utf-8")
    about_source = (root / "bookmark_organizer_pro/ui/about.py").read_text(encoding="utf-8")
    popup_source = (root / "browser-extension/popup.css").read_text(encoding="utf-8")
    smoke_source = inspect.getsource(smoke.run_desktop_smoke)
    browser_source = inspect.getsource(smoke.check_browser_layout)

    assert "self.btn_frame.pack(side=tk.BOTTOM" in editor_source
    assert "self.footer.pack(fill=tk.X, side=tk.BOTTOM)" in about_source
    assert "assert_widgets_do_not_overlap" in smoke_source
    assert "assert_combobox_uses_theme" in smoke_source
    assert "assert_widget_inside(about, about.footer" in smoke_source
    assert "-webkit-line-clamp" not in popup_source
    assert "helper text is still truncated" in browser_source


def test_root_minimum_allows_documented_laptop_viewport():
    root = Path(__file__).resolve().parents[1]
    app_source = (root / "bookmark_organizer_pro" / "app.py").read_text(encoding="utf-8")
    empty_state_source = (root / "bookmark_organizer_pro" / "ui" / "feedback.py").read_text(encoding="utf-8")
    assert "self.root.minsize(1180, 680)" in app_source
    assert 'self.bind("<Configure>", self._on_viewport_configure' in empty_state_source
    assert "int(event.height) < 680" in empty_state_source


def test_primary_dialog_headers_share_design_token():
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "bookmark_organizer_pro/ui/widget_bookmark_editor.py",
        "bookmark_organizer_pro/ui/widget_analytics.py",
        "bookmark_organizer_pro/ui/management_dialogs.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        assert "height=DesignTokens.HEADER_HEIGHT" in source


class TestThemeActivationIsChecked(unittest.TestCase):
    """R-156: a capture must not pass while the previous theme is on screen."""

    class _Manager:
        def __init__(self, *, applies=True, lands=True):
            self.applies = applies
            self.lands = lands
            self.current_theme = types.SimpleNamespace(name="github_dark")
            self.requested = []

        def set_theme(self, name):
            self.requested.append(name)
            if not self.applies:
                return False
            if self.lands:
                self.current_theme = types.SimpleNamespace(name=name)
            return True

    def test_a_manager_that_refuses_the_transition_fails_the_smoke(self):
        manager = self._Manager(applies=False)

        with self.assertRaises(smoke.VisualSmokeError) as raised:
            smoke._apply_theme(manager, "github_light")

        message = str(raised.exception)
        self.assertIn("github_light", message)
        self.assertIn("github_dark", message)

    def test_a_manager_that_reports_success_but_does_not_switch_fails(self):
        manager = self._Manager(lands=False)

        with self.assertRaises(smoke.VisualSmokeError) as raised:
            smoke._apply_theme(manager, "github_light")

        message = str(raised.exception)
        self.assertIn("github_light", message)
        self.assertIn("github_dark", message)

    def test_a_working_manager_passes(self):
        manager = self._Manager()

        smoke._apply_theme(manager, "github_light")

        self.assertEqual(["github_light"], manager.requested)
        self.assertEqual("github_light", manager.current_theme.name)

    def test_no_theme_transition_bypasses_the_guard(self):
        source = (
            Path(__file__).resolve().parents[1] / "scripts" / "visual_regression_smoke.py"
        ).read_text(encoding="utf-8")

        # The helper itself is the one place allowed to call set_theme.
        self.assertEqual(1, source.count("theme_manager.set_theme("))
        self.assertIn("def _apply_theme(theme_manager", source)


class _FakeUser32:
    """Records the Win32 calls the capture path makes.

    The offscreen contract is the thing under test, so it is exercised through
    a fake rather than by mapping a real window: a regression here is exactly
    what puts a window on the user's screen.
    """

    # Virtual desktop the fake reports: one 1920x1080 monitor at the origin.
    METRICS = {76: 0, 77: 0, 78: 1920, 79: 1080}

    def __init__(self, *, already_visible=False):
        self.already_visible = already_visible
        self.set_window_pos_calls = []
        self.show_window_calls = []
        self.placed = None
        self._visible = already_visible

    # ── queries ──
    def GetSystemMetrics(self, index):
        return self.METRICS[index]

    def GetAncestor(self, hwnd, _flag):
        return hwnd

    def IsWindowVisible(self, _hwnd):
        return 1 if self._visible else 0

    def GetForegroundWindow(self):
        return 4242

    def GetWindowLongW(self, _hwnd, _index):
        return 0

    def GetWindowRect(self, _hwnd, pointer):
        rect = pointer._obj
        left, top, width, height = self.placed
        rect.left, rect.top = left, top
        rect.right, rect.bottom = left + width, top + height
        return 1

    # ── mutations ──
    def SetWindowLongW(self, _hwnd, _index, _style):
        return 1

    def SetWindowPos(self, hwnd, insert_after, x, y, width, height, flags):
        self.set_window_pos_calls.append((hwnd, insert_after, x, y, width, height, flags))
        self.placed = (x, y, width, height)
        return 1

    def ShowWindow(self, hwnd, command):
        self.show_window_calls.append((hwnd, command))
        self._visible = True
        return 1

    def RedrawWindow(self, *_args):
        return 1

    def UpdateWindow(self, _hwnd):
        return 1


class _FakeWindow:
    """The narrow slice of a Tk window the capture path touches."""

    def __init__(self, hwnd=1001):
        self._hwnd = hwnd
        self.master = None
        self.updates = 0

    def winfo_id(self):
        return self._hwnd

    def update_idletasks(self):
        self.updates += 1

    def update(self):
        self.updates += 1

    def minsize(self):
        return (240, 180)

    def winfo_width(self):
        return 800

    def winfo_height(self):
        return 600

    def winfo_reqwidth(self):
        return 800

    def winfo_reqheight(self):
        return 600

    def attributes(self, *_args):
        return None


class TestCaptureStaysOffTheUsersScreen(unittest.TestCase):
    """R-202: a run must never put a window on the visible desktop."""

    def _prepare(self, *, already_visible):
        fake = _FakeUser32(already_visible=already_visible)
        with mock.patch.object(smoke.os, "name", "nt"), \
             mock.patch.object(smoke, "_user32", return_value=fake):
            hwnd = smoke._prepare_background_window(_FakeWindow())
        return fake, hwnd

    def test_a_hidden_window_is_positioned_outside_the_desktop(self):
        fake, _hwnd = self._prepare(already_visible=False)

        self.assertTrue(fake.set_window_pos_calls, "window was never positioned")
        x, y, width, height = fake.placed
        self.assertTrue(
            smoke._rect_is_offscreen(
                (x, y, x + width, y + height), (0, 0, 1920, 1080)
            ),
            f"placed at {fake.placed}, which is on the visible desktop",
        )

    def test_a_window_that_is_already_visible_is_still_moved(self):
        """The defect: an early return left these on the user's screen."""
        fake, _hwnd = self._prepare(already_visible=True)

        self.assertTrue(
            fake.set_window_pos_calls,
            "an already-visible window was shown without being moved offscreen",
        )
        x, y, width, height = fake.placed
        self.assertTrue(
            smoke._rect_is_offscreen((x, y, x + width, y + height), (0, 0, 1920, 1080))
        )

    def test_the_window_is_shown_without_being_activated(self):
        fake, _hwnd = self._prepare(already_visible=False)

        self.assertIn(4, [command for _hwnd, command in fake.show_window_calls],
                      "expected SW_SHOWNOACTIVATE")
        swp_noactivate = 0x0010
        for call in fake.set_window_pos_calls:
            self.assertTrue(call[-1] & swp_noactivate, f"SetWindowPos activated: {call}")

    def test_a_window_left_on_the_desktop_fails_the_run(self):
        fake = _FakeUser32()
        fake.placed = (100, 100, 800, 600)  # squarely on the visible desktop
        with mock.patch.object(smoke.os, "name", "nt"), \
             mock.patch.object(smoke, "_user32", return_value=fake):
            with self.assertRaises(smoke.VisualSmokeError) as raised:
                smoke._assert_window_offscreen(1001)

        self.assertIn("visible desktop", str(raised.exception))

    def test_no_capture_path_deiconifies_without_repositioning(self):
        source = (
            Path(__file__).resolve().parents[1] / "scripts" / "visual_regression_smoke.py"
        ).read_text(encoding="utf-8")

        # The only deiconify left is the non-Windows branch inside the helper,
        # where there is no virtual desktop to hide behind.
        self.assertEqual(1, source.count(".deiconify()"))
        helper = source.split("def _prepare_background_window")[1].split("\ndef ")[0]
        self.assertIn(".deiconify()", helper)

    def test_offscreen_geometry_covers_every_edge(self):
        bounds = (0, 0, 1920, 1080)

        self.assertTrue(smoke._rect_is_offscreen((-900, 0, -100, 600), bounds))
        self.assertTrue(smoke._rect_is_offscreen((1920, 0, 2720, 600), bounds))
        self.assertTrue(smoke._rect_is_offscreen((0, -700, 800, -100), bounds))
        self.assertFalse(smoke._rect_is_offscreen((0, 0, 800, 600), bounds))
        self.assertFalse(smoke._rect_is_offscreen((-100, 0, 100, 600), bounds))

    def test_a_run_that_stole_focus_fails(self):
        fake = _FakeUser32()
        with mock.patch.object(smoke.os, "name", "nt"), \
             mock.patch.object(smoke, "_user32", return_value=fake):
            smoke._assert_foreground_unchanged(4242)  # unchanged: fine
            with self.assertRaises(smoke.VisualSmokeError) as raised:
                smoke._assert_foreground_unchanged(9999)

        self.assertIn("foreground window", str(raised.exception))

    def test_an_unmeasurable_window_is_refused_rather_than_assumed_offscreen(self):
        """A failed GetWindowRect leaves a zero rect, which reads as offscreen."""
        fake = _FakeUser32()
        fake.placed = (0, 0, 0, 0)

        def failing_rect(_hwnd, _pointer):
            return 0

        fake.GetWindowRect = failing_rect
        with mock.patch.object(smoke.os, "name", "nt"), \
             mock.patch.object(smoke, "_user32", return_value=fake):
            with self.assertRaises(smoke.VisualSmokeError) as raised:
                smoke._assert_window_offscreen(1001)

        self.assertIn("GetWindowRect failed", str(raised.exception))

    def test_a_degenerate_rectangle_is_refused(self):
        """An all-zero rect passes _rect_is_offscreen against a desktop at 0,0."""
        self.assertTrue(smoke._rect_is_offscreen((0, 0, 0, 0), (0, 0, 1920, 1080)))

        fake = _FakeUser32()
        fake.placed = (0, 0, 0, 0)
        with mock.patch.object(smoke.os, "name", "nt"), \
             mock.patch.object(smoke, "_user32", return_value=fake):
            with self.assertRaises(smoke.VisualSmokeError) as raised:
                smoke._assert_window_offscreen(1001)

        self.assertIn("degenerate", str(raised.exception))

    def test_a_non_windows_run_refuses_a_display_someone_may_be_using(self):
        window = _FakeWindow()
        with mock.patch.object(smoke.os, "name", "posix"), \
             mock.patch.dict(smoke.os.environ, {"DISPLAY": ":0"}, clear=True):
            with self.assertRaises(smoke.VisualSmokeError) as raised:
                smoke._prepare_background_window(window)

        self.assertIn("virtual display", str(raised.exception))

    def test_a_non_windows_run_proceeds_on_a_virtual_display(self):
        for environment in (
            {"DISPLAY": ":99"},
            {"DISPLAY": ":7", "XVFB_DISPLAY": ":7"},
            {"BOP_VISUAL_SMOKE_VIRTUAL_DISPLAY": "1"},
        ):
            window = _FakeWindow()
            window.deiconify = lambda: None
            with mock.patch.object(smoke.os, "name", "posix"), \
                 mock.patch.dict(smoke.os.environ, environment, clear=True), \
                 mock.patch.object(smoke, "_get_toplevel_hwnd", return_value=1001):
                self.assertEqual(1001, smoke._prepare_background_window(window))

    def test_the_focus_contract_is_checked_even_when_the_run_fails(self):
        """A run that stole focus and then failed still reports the theft."""
        source = inspect.getsource(smoke.main)
        finally_block = source.split("finally:", 1)[1]

        self.assertIn("_assert_foreground_unchanged(foreground_before)", finally_block)

    def test_a_dialog_is_prepared_once(self):
        source = Path(smoke.__file__).read_text(encoding="utf-8")

        self.assertNotIn(
            "_prepare_background_window(credential_dialog)\n"
            "        _prepare_background_window(credential_dialog)",
            source,
        )
