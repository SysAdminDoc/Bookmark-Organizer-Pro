"""Dialog geometry and keyboard-accessibility contracts."""

from pathlib import Path

from bookmark_organizer_pro.ui.window_geometry import fit_window_geometry


ROOT = Path(__file__).resolve().parents[1]


def test_dialog_geometry_fits_supported_laptop_viewport():
    geometry = fit_window_geometry(640, 760, 1280, 720)
    assert geometry.width == 640
    assert geometry.height <= 672
    assert geometry.x >= 24
    assert geometry.y >= 24
    assert geometry.x + geometry.width <= 1280 - 24
    assert geometry.y + geometry.height <= 720 - 24


def test_mouse_only_labels_use_shared_keyboard_activation():
    shell = (ROOT / "bookmark_organizer_pro/app_mixins/app_shell.py").read_text(
        encoding="utf-8"
    )
    editor = (ROOT / "bookmark_organizer_pro/ui/widget_bookmark_editor.py").read_text(
        encoding="utf-8"
    )
    assert "make_keyboard_activatable(self._nl_toggle_btn" in shell
    assert "make_keyboard_activatable(add_btn, add_ai_tags)" in editor


def test_bookmark_editor_uses_scrollable_body_and_fixed_footer():
    source = (ROOT / "bookmark_organizer_pro/ui/widget_bookmark_editor.py").read_text(
        encoding="utf-8"
    )
    assert "self.content_canvas" in source
    assert 'self.bind("<Prior>"' in source
    assert 'self.bind("<Next>"' in source
    assert "btn_frame = tk.Frame(self" in source

