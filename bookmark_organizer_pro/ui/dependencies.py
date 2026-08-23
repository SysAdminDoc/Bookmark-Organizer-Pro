"""First-run dependency check dialog."""

from __future__ import annotations

import tkinter as tk

from bookmark_organizer_pro.constants import APP_NAME
from bookmark_organizer_pro.i18n import _, format_message
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.utils.dependencies import DependencyManager

from .foundation import FONTS
from .widgets import ModernButton, apply_window_chrome, get_theme
from .window_geometry import apply_screen_aware_geometry


class DependencyCheckDialog(tk.Toplevel):
    """Report unresolved dependencies and external repair guidance."""

    def __init__(self, parent: tk.Tk, dep_manager: DependencyManager):
        super().__init__(parent)
        self.parent = parent
        self.dep_manager = dep_manager
        self.result = False

        theme = get_theme()

        self.title(format_message('{value_0}: Setup Check', value_0=APP_NAME))
        apply_screen_aware_geometry(self, 640, 500)
        self.minsize(520, 420)
        self.resizable(True, True)
        self.configure(bg=theme.bg_primary)
        apply_window_chrome(self)

        self.transient(parent)
        self.grab_set()
        self.bind("<Escape>", lambda e: self._on_cancel())

        self._create_ui(theme)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _create_ui(self, theme) -> None:
        header = tk.Frame(self, bg=theme.bg_secondary, padx=20, pady=15)
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text=_("Setup Check"),
            font=FONTS.subtitle(bold=True),
            bg=theme.bg_secondary,
            fg=theme.text_primary,
        ).pack(anchor="w")

        tk.Label(
            header,
            text=self.dep_manager.repair_guidance(),
            font=FONTS.small(),
            bg=theme.bg_secondary,
            fg=theme.text_secondary,
            wraplength=580,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(5, 0))

        self.footer = tk.Frame(self, bg=theme.bg_secondary, padx=20, pady=15)
        self.footer.pack(fill=tk.X, side=tk.BOTTOM)

        self.skip_btn = None
        if not self.dep_manager.missing_required:
            self.skip_btn = ModernButton(
                self.footer,
                text=_("Continue Without Optional"),
                font=FONTS.small(),
                padx=15,
                pady=8,
                command=self._on_skip,
            )
            self.skip_btn.pack(side=tk.RIGHT, padx=(0, 10))

        self.cancel_btn = ModernButton(
            self.footer,
            text=_("Close") if self.dep_manager.missing_required else _("Cancel"),
            font=FONTS.small(),
            padx=15,
            pady=8,
            command=self._on_cancel,
        )
        self.cancel_btn.pack(side=tk.LEFT)

        self.content = tk.Frame(self, bg=theme.bg_primary, padx=20, pady=15)
        self.content.pack(fill=tk.BOTH, expand=True)

        if self.dep_manager.missing_required:
            tk.Label(
                self.content,
                text=_("Required Packages"),
                font=FONTS.small(bold=True),
                bg=theme.bg_primary,
                fg=theme.accent_error,
            ).pack(anchor="w", pady=(0, 5))

            for package in self.dep_manager.missing_required:
                info = self.dep_manager.REQUIRED_PACKAGES[package]
                frame = tk.Frame(self.content, bg=theme.bg_primary)
                frame.pack(fill=tk.X, pady=(2, 5))
                tk.Label(
                    frame,
                    text=format_message('Required: {value_0}', value_0=package),
                    font=FONTS.small(),
                    bg=theme.bg_primary,
                    fg=theme.text_primary,
                ).pack(anchor="w")
                tk.Label(
                    frame,
                    text=format_message('{value_0}', value_0=info['description']),
                    font=FONTS.tiny(),
                    bg=theme.bg_primary,
                    fg=theme.text_muted,
                    wraplength=560,
                    justify=tk.LEFT,
                ).pack(anchor="w", padx=(16, 0), pady=(2, 0))

        if self.dep_manager.missing_optional:
            tk.Label(
                self.content,
                text=_("Optional Packages"),
                font=FONTS.small(bold=True),
                bg=theme.bg_primary,
                fg=theme.accent_warning,
            ).pack(anchor="w", pady=(15, 5))

            for package in self.dep_manager.missing_optional:
                info = self.dep_manager.OPTIONAL_PACKAGES[package]
                frame = tk.Frame(self.content, bg=theme.bg_primary)
                frame.pack(fill=tk.X, pady=(2, 5))
                tk.Label(
                    frame,
                    text=format_message('Optional: {value_0}', value_0=package),
                    font=FONTS.small(),
                    bg=theme.bg_primary,
                    fg=theme.text_primary,
                ).pack(anchor="w")
                tk.Label(
                    frame,
                    text=format_message('{value_0}', value_0=info['description']),
                    font=FONTS.tiny(),
                    bg=theme.bg_primary,
                    fg=theme.text_muted,
                    wraplength=560,
                    justify=tk.LEFT,
                ).pack(anchor="w", padx=(16, 0), pady=(2, 0))

    def _on_skip(self) -> None:
        self.result = True
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = False
        self.destroy()


def check_and_install_dependencies(root: tk.Tk) -> bool:
    """Check runtime dependencies and show the setup dialog when needed."""
    dep_manager = DependencyManager()
    all_ok, missing_required, missing_optional = dep_manager.check_all()

    if all_ok and not missing_optional:
        log.info("All dependencies satisfied")
        return True

    if not missing_required and not missing_optional:
        return True

    dialog = DependencyCheckDialog(root, dep_manager)
    root.wait_window(dialog)
    return dialog.result
