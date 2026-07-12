import inspect
from pathlib import Path

from PIL import Image

from scripts import visual_regression_smoke as smoke


def test_visual_smoke_surface_matrix_covers_required_desktop_and_extension_views():
    assert {
        "desktop-main-empty-dark",
        "desktop-main-list-light",
        "desktop-assistant-settings",
        "desktop-import-progress",
        "desktop-cleanup-review",
        "desktop-read-later-queue",
        "desktop-snapshot-failures-sidebar",
        "desktop-export-dialog",
        "desktop-reader-view",
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


def test_windows_capture_resolves_top_level_hwnd_contract():
    source = inspect.getsource(smoke._get_toplevel_hwnd)
    assert "GetAncestor" in source
    assert "winfo_id" in source


def test_desktop_viewport_gate_covers_supported_sizes_and_themes():
    source = inspect.getsource(smoke.verify_desktop_viewports)
    assert "(1280, 720)" in source
    assert "(1540, 980)" in source
    assert "(1920, 1080)" in source
    assert '"github_dark"' in source
    assert '"github_light"' in source
    assert "assert_actionable_controls_inside" in source


def test_primary_dialog_headers_share_design_token():
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "bookmark_organizer_pro/ui/widget_bookmark_editor.py",
        "bookmark_organizer_pro/ui/widget_analytics.py",
        "bookmark_organizer_pro/ui/management_dialogs.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        assert "height=DesignTokens.HEADER_HEIGHT" in source
