"""Recovery behavior for inaccessible persisted and imported themes."""

from __future__ import annotations

import json

from bookmark_organizer_pro.ui.theme import ThemeColors, ThemeInfo, ThemeManager


def test_inaccessible_persisted_theme_is_skipped_and_safe_theme_remains_active(tmp_path):
    themes = tmp_path / "themes"
    themes.mkdir()
    (themes / "unsafe.json").write_text(
        json.dumps({
            "name": "unsafe",
            "display_name": "Unsafe",
            "colors": {"text_primary": "#ffffff", "bg_primary": "#ffffff"},
        }),
        encoding="utf-8",
    )
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"theme": "unsafe"}), encoding="utf-8")
    built_in = {"base": ThemeInfo("base", "Base", colors=ThemeColors())}

    manager = ThemeManager(
        built_in,
        settings_file=settings,
        themes_dir=themes,
        default_theme="base",
    )

    assert manager.current_theme.name == "base"
    assert "unsafe" not in manager.custom_themes
    assert "unsafe.json" in manager.rejected_custom_themes
    assert "Primary text" in manager.rejected_custom_themes["unsafe.json"]


def test_import_rejection_exposes_contrast_reason_without_changing_theme(tmp_path):
    built_in = {"base": ThemeInfo("base", "Base", colors=ThemeColors())}
    manager = ThemeManager(
        built_in,
        settings_file=tmp_path / "settings.json",
        themes_dir=tmp_path / "themes",
        default_theme="base",
    )
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(
        json.dumps({
            "name": "unsafe",
            "display_name": "Unsafe",
            "colors": {"text_primary": "#ffffff", "bg_primary": "#ffffff"},
        }),
        encoding="utf-8",
    )

    assert manager.import_theme(unsafe) is None
    assert manager.current_theme.name == "base"
    assert "Primary text" in manager.last_import_error
