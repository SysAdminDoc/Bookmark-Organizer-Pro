"""First-run dependency check dialog."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from bookmark_organizer_pro.constants import APP_NAME
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.utils.dependencies import DependencyManager

from .foundation import FONTS


class DependencyCheckDialog(tk.Toplevel):
    """Dialog for checking and installing first-run Python dependencies."""

    def __init__(self, parent: tk.Tk, dep_manager: DependencyManager):
        super().__init__(parent)
        self.parent = parent
        self.dep_manager = dep_manager
        self.result = False

        self.title(f"{APP_NAME} - Dependency Check")
        self.geometry("500x400")
        self.resizable(False, False)
        self.configure(bg="#1e1e2e")

        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        x = (self.winfo_screenwidth() - 500) // 2
        y = (self.winfo_screenheight() - 400) // 2
        self.geometry(f"+{x}+{y}")

        self._create_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _create_ui(self) -> None:
        header = tk.Frame(self, bg="#313244", padx=20, pady=15)
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text="Dependency Check",
            font=(FONTS.family, 14, "bold"),
            bg="#313244",
            fg="#cdd6f4",
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Some packages need to be installed for full functionality.",
            font=(FONTS.family, 10),
            bg="#313244",
            fg="#a6adc8",
        ).pack(anchor="w", pady=(5, 0))

        content = tk.Frame(self, bg="#1e1e2e", padx=20, pady=15)
        content.pack(fill=tk.BOTH, expand=True)

        if self.dep_manager.missing_required:
            tk.Label(
                content,
                text="Required Packages",
                font=(FONTS.family, 10, "bold"),
                bg="#1e1e2e",
                fg="#f38ba8",
            ).pack(anchor="w", pady=(0, 5))

            for package in self.dep_manager.missing_required:
                info = self.dep_manager.REQUIRED_PACKAGES[package]
                frame = tk.Frame(content, bg="#1e1e2e")
                frame.pack(fill=tk.X, pady=2)
                tk.Label(
                    frame,
                    text=f"Required: {package}",
                    font=(FONTS.family, 10),
                    bg="#1e1e2e",
                    fg="#cdd6f4",
                ).pack(side=tk.LEFT)
                tk.Label(
                    frame,
                    text=f"- {info['description']}",
                    font=(FONTS.family, 9),
                    bg="#1e1e2e",
                    fg="#6c7086",
                ).pack(side=tk.LEFT, padx=(10, 0))

        if self.dep_manager.missing_optional:
            tk.Label(
                content,
                text="Optional Packages",
                font=(FONTS.family, 10, "bold"),
                bg="#1e1e2e",
                fg="#f9e2af",
            ).pack(anchor="w", pady=(15, 5))

            for package in self.dep_manager.missing_optional:
                info = self.dep_manager.OPTIONAL_PACKAGES[package]
                frame = tk.Frame(content, bg="#1e1e2e")
                frame.pack(fill=tk.X, pady=2)
                tk.Label(
                    frame,
                    text=f"Optional: {package}",
                    font=(FONTS.family, 10),
                    bg="#1e1e2e",
                    fg="#cdd6f4",
                ).pack(side=tk.LEFT)
                tk.Label(
                    frame,
                    text=f"- {info['description']}",
                    font=(FONTS.family, 9),
                    bg="#1e1e2e",
                    fg="#6c7086",
                ).pack(side=tk.LEFT, padx=(10, 0))

        self.progress_frame = tk.Frame(content, bg="#1e1e2e")
        self.progress_frame.pack(fill=tk.X, pady=(20, 0))

        self.progress_label = tk.Label(
            self.progress_frame,
            text="",
            font=(FONTS.family, 9),
            bg="#1e1e2e",
            fg="#a6adc8",
        )
        self.progress_label.pack(anchor="w")

        self.progress_bar = ttk.Progressbar(self.progress_frame, mode="indeterminate", length=300)

        btn_frame = tk.Frame(self, bg="#313244", padx=20, pady=15)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.install_btn = tk.Button(
            btn_frame,
            text="Install All",
            font=(FONTS.family, 10),
            bg="#89b4fa",
            fg="#1e1e2e",
            activebackground="#b4befe",
            activeforeground="#1e1e2e",
            relief=tk.FLAT,
            padx=20,
            pady=8,
            cursor="hand2",
            command=self._on_install,
        )
        self.install_btn.pack(side=tk.RIGHT)

        if not self.dep_manager.missing_required:
            self.skip_btn = tk.Button(
                btn_frame,
                text="Continue Without Optional",
                font=(FONTS.family, 10),
                bg="#45475a",
                fg="#cdd6f4",
                activebackground="#585b70",
                activeforeground="#cdd6f4",
                relief=tk.FLAT,
                padx=15,
                pady=8,
                cursor="hand2",
                command=self._on_skip,
            )
            self.skip_btn.pack(side=tk.RIGHT, padx=(0, 10))

        tk.Button(
            btn_frame,
            text="Cancel",
            font=(FONTS.family, 10),
            bg="#45475a",
            fg="#cdd6f4",
            activebackground="#585b70",
            activeforeground="#cdd6f4",
            relief=tk.FLAT,
            padx=15,
            pady=8,
            cursor="hand2",
            command=self._on_cancel,
        ).pack(side=tk.LEFT)

    def _on_install(self) -> None:
        self.install_btn.configure(state=tk.DISABLED)
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

        if success or not self.dep_manager.missing_required:
            self.progress_label.configure(text="Installation complete.", fg="#a6e3a1")
            self.result = True
            self.after(1000, self.destroy)
            return

        self.progress_label.configure(
            text="Some installations failed. Check your internet connection.",
            fg="#f38ba8",
        )
        self.install_btn.configure(state=tk.NORMAL, text="Retry")

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
