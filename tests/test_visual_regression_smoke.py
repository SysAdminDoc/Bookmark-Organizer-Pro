import inspect
from pathlib import Path

from PIL import Image

from scripts import visual_regression_smoke as smoke


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
