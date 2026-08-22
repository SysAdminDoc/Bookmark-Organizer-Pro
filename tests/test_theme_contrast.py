"""Every built-in theme must clear WCAG AA on the pairs the desktop actually draws.

Only pairs that some widget really renders are asserted here. `colors.selected`,
for instance, is a button hover/press background rather than a text surface, so
it is checked through the ttk mapping that draws on it instead of against
`text_primary`.
"""

from __future__ import annotations

import unittest

from bookmark_organizer_pro.theme_runtime import BUILT_IN_THEMES
from bookmark_organizer_pro.ui.foundation import contrast_ratio, readable_text_on
from bookmark_organizer_pro.ui.style_manager import StyleManager

AA_TEXT = 4.5

# Surfaces that body/label text is drawn on.
TEXT_SURFACES = (
    "bg_primary", "bg_secondary", "bg_card", "bg_dark", "bg_tertiary", "bg_hover",
)
BODY_INK = ("text_primary", "text_secondary", "text_muted")
# Accent inks only ever appear on the two main panel surfaces.
ACCENT_INK = ("text_link", "status_success", "status_warning", "status_error", "status_info")
ACCENT_SURFACES = ("bg_primary", "bg_secondary")


class _RecordingStyle:
    """Captures ttk style calls so the mapping can be asserted without Tk."""

    def __init__(self):
        self.maps = {}
        self.configs = {}

    def configure(self, name, **kwargs):
        self.configs.setdefault(name, {}).update(kwargs)

    def map(self, name, **kwargs):
        self.maps.setdefault(name, {}).update(kwargs)

    def theme_use(self, *args, **kwargs):
        return "clam"

    def theme_names(self):
        return ("clam",)

    def lookup(self, *args, **kwargs):
        return ""

    def layout(self, *args, **kwargs):
        return []


def _style_for(colors) -> _RecordingStyle:
    recording = _RecordingStyle()
    manager = StyleManager.__new__(StyleManager)
    manager._initialized = True
    manager.root = None
    manager.style = recording
    manager._current_theme_colors = None
    manager._sv_ttk = None
    manager._sv_ttk_enabled = False
    manager._base_theme_name = ""
    manager._base_theme_error = ""
    manager.apply_theme(colors)
    return recording


class TestThemeContrast(unittest.TestCase):
    def test_body_text_clears_aa_on_every_surface_it_is_drawn_on(self):
        for key, info in BUILT_IN_THEMES.items():
            colors = info.colors
            for ink in BODY_INK:
                for surface in TEXT_SURFACES:
                    with self.subTest(theme=key, ink=ink, surface=surface):
                        ratio = contrast_ratio(getattr(colors, ink), getattr(colors, surface))
                        self.assertGreaterEqual(
                            ratio, AA_TEXT,
                            f"{key}: {ink} {getattr(colors, ink)} on {surface} "
                            f"{getattr(colors, surface)} is {ratio:.2f}",
                        )

    def test_accent_and_status_text_clears_aa_on_panel_surfaces(self):
        for key, info in BUILT_IN_THEMES.items():
            colors = info.colors
            for ink in ACCENT_INK:
                for surface in ACCENT_SURFACES:
                    with self.subTest(theme=key, ink=ink, surface=surface):
                        ratio = contrast_ratio(getattr(colors, ink), getattr(colors, surface))
                        self.assertGreaterEqual(
                            ratio, AA_TEXT,
                            f"{key}: {ink} {getattr(colors, ink)} on {surface} "
                            f"{getattr(colors, surface)} is {ratio:.2f}",
                        )

    def test_menu_selection_keeps_its_label_readable(self):
        """Menus set activebackground=selection with activeforeground=text_primary."""
        for key, info in BUILT_IN_THEMES.items():
            colors = info.colors
            with self.subTest(theme=key):
                ratio = contrast_ratio(colors.text_primary, colors.selection)
                self.assertGreaterEqual(
                    ratio, AA_TEXT,
                    f"{key}: text_primary on selection is {ratio:.2f}",
                )

    def test_primary_button_recomputes_its_ink_for_hover_and_press(self):
        """`Primary.TButton` swaps its background to `selected` when hovered or
        pressed. Leaving the resting ink in place drops the label under AA on
        most themes, so the foreground must be mapped for those states too."""
        for key, info in BUILT_IN_THEMES.items():
            colors = info.colors
            mapping = _style_for(colors).maps.get("Primary.TButton", {})
            foreground = dict(mapping.get("foreground", []))
            with self.subTest(theme=key):
                for state in ("pressed", "active"):
                    self.assertIn(
                        state, foreground,
                        f"{key}: Primary.TButton must map its foreground for {state}",
                    )
                    ratio = contrast_ratio(foreground[state], colors.selected)
                    self.assertGreaterEqual(
                        ratio, AA_TEXT,
                        f"{key}: {state} ink {foreground[state]} on selected "
                        f"{colors.selected} is {ratio:.2f}",
                    )

    def test_readable_text_on_picks_the_higher_contrast_ink(self):
        for key, info in BUILT_IN_THEMES.items():
            for token in ("accent_primary", "selected", "accent_error", "accent_success"):
                background = getattr(info.colors, token)
                with self.subTest(theme=key, token=token):
                    self.assertGreaterEqual(
                        contrast_ratio(readable_text_on(background), background), AA_TEXT,
                        f"{key}: no readable ink for {token} {background}",
                    )


if __name__ == "__main__":
    unittest.main()
