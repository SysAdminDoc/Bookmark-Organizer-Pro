"""First-run dependency check dialog."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

from bookmark_organizer_pro.constants import APP_NAME
from bookmark_organizer_pro.i18n import _, format_message
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.utils.dependencies import DependencyInstallReport, DependencyManager

from .foundation import FONTS
from .widgets import ModernButton, apply_window_chrome, get_theme
from .window_geometry import apply_screen_aware_geometry


class DependencyCheckDialog(tk.Toplevel):
    """Dialog for checking and installing first-run Python dependencies."""

    def __init__(self, parent: tk.Tk, dep_manager: DependencyManager):
        super().__init__(parent)
        self.parent = parent
        self.dep_manager = dep_manager
        self.result = False
        self._installing = False
        self._cancel_requested = False
        self._closed = False
        self._ui_queue: queue.Queue = queue.Queue()

        theme = get_theme()

        self.title(format_message('{value_0} - Setup Check', value_0=APP_NAME))
        apply_screen_aware_geometry(self, 500, 400)
        self.minsize(420, 340)
        self.resizable(True, True)
        self.configure(bg=theme.bg_primary)
        apply_window_chrome(self)

        self.transient(parent)
        self.grab_set()
        self.bind("<Escape>", lambda e: self._on_cancel())

        self._create_ui(theme)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.after(50, self._drain_ui_queue)

    def _create_ui(self, theme) -> None:
        install_supported = self.dep_manager.runtime_install_supported
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
            text=(
                _("Install required packages now, or continue with optional features disabled.")
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
                text=_("Required Packages"),
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
                    text=format_message('Required: {value_0}', value_0=package),
                    font=FONTS.small(),
                    bg=theme.bg_primary,
                    fg=theme.text_primary,
                ).pack(side=tk.LEFT)
                tk.Label(
                    frame,
                    text=format_message('- {value_0}', value_0=info['description']),
                    font=FONTS.tiny(),
                    bg=theme.bg_primary,
                    fg=theme.text_muted,
                ).pack(side=tk.LEFT, padx=(10, 0))

        if self.dep_manager.missing_optional:
            tk.Label(
                content,
                text=_("Optional Packages"),
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
                    text=format_message('Optional: {value_0}', value_0=package),
                    font=FONTS.small(),
                    bg=theme.bg_primary,
                    fg=theme.text_primary,
                ).pack(side=tk.LEFT)
                tk.Label(
                    frame,
                    text=format_message('- {value_0}', value_0=info['description']),
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
                text=_("Install All"),
                font=FONTS.small(),
                style="primary",
                padx=20,
                pady=8,
                command=self._on_install,
            )
            self.install_btn.pack(side=tk.RIGHT)

        self.skip_btn = None
        if not self.dep_manager.missing_required:
            self.skip_btn = ModernButton(
                btn_frame,
                text=_("Continue Without Optional"),
                font=FONTS.small(),
                padx=15,
                pady=8,
                command=self._on_skip,
            )
            self.skip_btn.pack(side=tk.RIGHT, padx=(0, 10))

        self.cancel_btn = ModernButton(
            btn_frame,
            text=_("Cancel"),
            font=FONTS.small(),
            padx=15,
            pady=8,
            command=self._on_cancel,
        )
        self.cancel_btn.pack(side=tk.LEFT)

    def _post_ui(self, callback) -> None:
        if self._closed:
            return
        self._ui_queue.put(callback)

    def _drain_ui_queue(self) -> None:
        if self._closed:
            return
        while True:
            try:
                callback = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except tk.TclError:
                self._closed = True
                return
        self.after(50, self._drain_ui_queue)

    def _on_destroy(self, event) -> None:
        if event.widget is self:
            self._closed = True

    def _on_install(self) -> None:
        if self.install_btn is None:
            self.progress_label.configure(
                text=self.dep_manager.repair_guidance(),
                fg=self._theme.accent_error,
            )
            return
        self.install_btn.set_state("disabled")
        if self.skip_btn is not None:
            self.skip_btn.set_state("disabled")
        self._installing = True
        self._cancel_requested = False
        self.cancel_btn.set_text("Cancel")
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))
        self.progress_bar.start(10)

        def do_install():
            success = self.dep_manager.install_all_missing(
                progress_callback=lambda msg: self._post_ui(
                    lambda message=msg: self.progress_label.configure(text=message),
                )
            )
            report = self.dep_manager.last_install_report
            self._post_ui(lambda: self._installation_complete(success, report))

        threading.Thread(target=do_install, daemon=True).start()

    def _installation_complete(self, success: bool, report: DependencyInstallReport) -> None:
        self._installing = False
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        theme = self._theme

        if report.cancelled:
            self.progress_label.configure(text=report.summary(), fg=theme.accent_warning)
            self.cancel_btn.set_text("Close")
            if self.install_btn is not None:
                self.install_btn.set_state("normal")
                self.install_btn.set_text("Retry Remaining")
            if self.skip_btn is not None:
                self.skip_btn.set_state("normal")
            return

        if success or not self.dep_manager.missing_required:
            self.progress_label.configure(text=_("Installation complete."), fg=theme.accent_success)
            self.result = True
            self.after(1000, self.destroy)
            return

        self.progress_label.configure(
            text=_("Some installations failed. Check your internet connection."),
            fg=theme.accent_error,
        )
        self.install_btn.set_state("normal")
        self.install_btn.set_text("Retry")

    def _on_skip(self) -> None:
        self.result = True
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = False
        if not self._installing:
            self.destroy()
            return
        if self._cancel_requested:
            return
        self._cancel_requested = True
        self.progress_label.configure(
            text=_("Cancelling installer safely..."),
            fg=self._theme.accent_warning,
        )
        self.cancel_btn.set_state("disabled")

        def cancel_worker():
            self.dep_manager.cancel_installation()
            self._post_ui(lambda: self.cancel_btn.set_state("normal"))

        threading.Thread(target=cancel_worker, daemon=True).start()


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
