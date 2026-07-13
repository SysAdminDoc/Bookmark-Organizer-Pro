"""First-run dependency check dialog."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from bookmark_organizer_pro.constants import APP_NAME
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.utils.dependencies import DependencyManager

from .foundation import FONTS
from .window_geometry import apply_screen_aware_geometry
from .widgets import ModernButton, apply_window_chrome, get_theme


class DependencyCheckDialog(tk.Toplevel):
    """Dialog for checking and installing first-run Python dependencies."""

    def __init__(self, parent: tk.Tk, dep_manager: DependencyManager):
        super().__init__(parent)
        self.parent = parent
        self.dep_manager = dep_manager
        self.result = False

        theme = get_theme()

        self.title(f"{APP_NAME} - Setup Check")
        apply_screen_aware_geometry(self, 500, 400)
        self.minsize(420, 340)
        self.resizable(True, True)
        self.configure(bg=theme.bg_primary)
        apply_window_chrome(self)

        self.transient(parent)
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())

        self._create_ui(theme)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _create_ui(self, theme) -> None:
        install_supported = self.dep_manager.runtime_install_supported
        header = tk.Frame(self, bg=theme.bg_secondary, padx=20, pady=15)
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text="Setup Check",
            font=FONTS.subtitle(bold=True),
            bg=theme.bg_secondary,
            fg=theme.text_primary,
        ).pack(anchor="w")

        tk.Label(
            header,
            text=(
                "Install required packages now, or continue with optional features disabled."
                if install_supported
                else self.dep_manager.repair_guidance()
            ),
            font=FONTS.small(),
            bg=theme.bg_secondary,
            fg=theme.text_secondary,
            wraplength=450,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(5, 0))

        content = tk.Frame(self, bg=theme.bg_primary, padx=20, pady=15)
        content.pack(fill=tk.BOTH, expand=True)

        if self.dep_manager.missing_required:
            tk.Label(
                content,
                text="Required Packages",
                font=FONTS.small(bold=True),
                bg=theme.bg_primary,
                fg=theme.accent_error,
            ).pack(anchor="w", pady=(0, 5))

            for package in self.dep_manager.missing_required:
                info = self.dep_manager.REQUIRED_PACKAGES[package]
                frame = tk.Frame(content, bg=theme.bg_primary)
                frame.pack(fill=tk.X, pady=2)
                tk.Label(
                    frame,
                    text=f"Required: {package}",
                    font=FONTS.small(),
                    bg=theme.bg_primary,
                    fg=theme.text_primary,
                ).pack(side=tk.LEFT)
                tk.Label(
                    frame,
                    text=f"- {info['description']}",
                    font=FONTS.tiny(),
                    bg=theme.bg_primary,
                    fg=theme.text_muted,
                ).pack(side=tk.LEFT, padx=(10, 0))

        if self.dep_manager.missing_optional:
            tk.Label(
                content,
                text="Optional Packages",
                font=FONTS.small(bold=True),
                bg=theme.bg_primary,
                fg=theme.accent_warning,
            ).pack(anchor="w", pady=(15, 5))

            for package in self.dep_manager.missing_optional:
                info = self.dep_manager.OPTIONAL_PACKAGES[package]
                frame = tk.Frame(content, bg=theme.bg_primary)
                frame.pack(fill=tk.X, pady=2)
                tk.Label(
                    frame,
                    text=f"Optional: {package}",
                    font=FONTS.small(),
                    bg=theme.bg_primary,
                    fg=theme.text_primary,
                ).pack(side=tk.LEFT)
                tk.Label(
                    frame,
                    text=f"- {info['description']}",
                    font=FONTS.tiny(),
                    bg=theme.bg_primary,
                    fg=theme.text_muted,
                ).pack(side=tk.LEFT, padx=(10, 0))

        self.progress_frame = tk.Frame(content, bg=theme.bg_primary)
        self.progress_frame.pack(fill=tk.X, pady=(20, 0))

        self.progress_label = tk.Label(
            self.progress_frame,
            text="",
            font=FONTS.tiny(),
            bg=theme.bg_primary,
            fg=theme.text_secondary,
        )
        self.progress_label.pack(anchor="w")

        self.progress_bar = ttk.Progressbar(self.progress_frame, mode="indeterminate", length=300)

        btn_frame = tk.Frame(self, bg=theme.bg_secondary, padx=20, pady=15)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self._theme = theme

        self.install_btn = None
        if install_supported:
            self.install_btn = ModernButton(
                btn_frame,
                text="Install All",
                font=FONTS.small(),
                style="primary",
                padx=20,
                pady=8,
                command=self._on_install,
            )
            self.install_btn.pack(side=tk.RIGHT)

        if not self.dep_manager.missing_required:
            self.skip_btn = ModernButton(
                btn_frame,
                text="Continue Without Optional",
                font=FONTS.small(),
                padx=15,
                pady=8,
                command=self._on_skip,
            )
            self.skip_btn.pack(side=tk.RIGHT, padx=(0, 10))

        ModernButton(
            btn_frame,
            text="Cancel",
            font=FONTS.small(),
            padx=15,
            pady=8,
            command=self._on_cancel,
        ).pack(side=tk.LEFT)

    def _on_install(self) -> None:
        if self.install_btn is None:
            self.progress_label.configure(
                text=self.dep_manager.repair_guidance(),
                fg=self._theme.accent_error,
            )
            return
        self.install_btn.set_state("disabled")
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))
        self.progress_bar.start(10)

        def do_install():
            success = self.dep_manager.install_all_missing(
                progress_callback=lambda msg: self.after(
                    0,
                    lambda: self.progress_label.configure(text=msg),
                )
            )
            self.after(0, lambda: self._installation_complete(success))

        threading.Thread(target=do_install, daemon=True).start()

    def _installation_complete(self, success: bool) -> None:
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        theme = self._theme

        if success or not self.dep_manager.missing_required:
            self.progress_label.configure(text="Installation complete.", fg=theme.accent_success)
            self.result = True
            self.after(1000, self.destroy)
            return

        self.progress_label.configure(
            text="Some installations failed. Check your internet connection.",
            fg=theme.accent_error,
        )
        self.install_btn.set_state("normal")
        self.install_btn.set_text("Retry")

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
