"""Desktop launcher entry point for Bookmark Organizer Pro."""

from __future__ import annotations

import multiprocessing
import os
import sys
import tkinter as tk
from tkinter import messagebox
from typing import Sequence

from bookmark_organizer_pro.cli import BookmarkCLI
from bookmark_organizer_pro.constants import IS_WINDOWS, LOG_FILE, ensure_directories
from bookmark_organizer_pro.desktop_bootstrap import (
    import_dependencies,
    set_dark_title_bar,
    setup_dpi_awareness,
)
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.services.egress import egress_summary_line
from bookmark_organizer_pro.i18n import setup_locale
from bookmark_organizer_pro.ui import check_and_install_dependencies
from bookmark_organizer_pro.ui.style_manager import style_manager
from bookmark_organizer_pro.ui.tk_interactions import make_keyboard_activatable
from bookmark_organizer_pro.ui.widgets import set_widget_window_chrome_provider


def _show_first_run_privacy_notice(root: tk.Tk):
    """Show a one-time privacy banner at the top of the window (non-modal)."""
    from bookmark_organizer_pro.constants import SETTINGS_FILE
    from bookmark_organizer_pro.services.settings_store import SettingsStore
    from bookmark_organizer_pro.ui.foundation import FONTS, readable_text_on
    settings_store = SettingsStore(SETTINGS_FILE)
    try:
        settings_snapshot = settings_store.read()
        if settings_snapshot.get("privacy_notice_shown"):
            return
    except Exception as exc:
        log.warning(f"Could not load privacy-notice preference: {exc}")
        settings_snapshot = None

    def _dismiss_banner():
        banner.destroy()
        try:
            settings_store.set(
                "privacy_notice_shown",
                True,
                base_snapshot=settings_snapshot,
            )
        except Exception as exc:
            log.warning(f"Could not save privacy-notice preference: {exc}")

    try:
        from bookmark_organizer_pro.theme_runtime import get_theme
        theme = get_theme()
        accent = theme.accent_primary
    except Exception:
        accent = "#0f766e"
    accent_fg = readable_text_on(accent)
    banner = tk.Frame(root, bg=accent, height=40)
    banner.pack(fill=tk.X, side=tk.TOP)
    banner.pack_propagate(False)

    tk.Label(
        banner,
        text=egress_summary_line(),
        bg=accent, fg=accent_fg, font=FONTS.small(),
        anchor="w",
    ).pack(side=tk.LEFT, padx=(16, 8), fill=tk.Y)

    dismiss_btn = tk.Label(
        banner, text="Got it", bg=accent, fg=accent_fg,
        font=FONTS.small(bold=True), cursor="hand2", padx=12,
    )
    dismiss_btn.pack(side=tk.RIGHT, padx=(0, 12), fill=tk.Y)
    make_keyboard_activatable(
        dismiss_btn, _dismiss_banner, accessible_name="Dismiss privacy notice"
    )


def _configure_tk_scaling(root: tk.Tk):
    """Apply Tk scaling for high-DPI displays when Tk reports a larger DPI."""
    try:
        dpi = root.winfo_fpixels('1i')
        scale = dpi / 96.0
        if scale > 1.0:
            root.tk.call('tk', 'scaling', scale)
            log.debug(f"Set tk scaling to {scale} (DPI: {dpi})")
    except Exception as e:
        log.warning(f"Could not set tk scaling: {e}")


def main(argv: Sequence[str] | None = None):
    """Run the CLI or desktop GUI with professional error handling."""
    ensure_directories()
    args = list(sys.argv[1:] if argv is None else argv)
    setup_locale(os.environ.get("BOOKMARK_LOCALE", ""))

    if IS_WINDOWS:
        multiprocessing.freeze_support()
    setup_dpi_awareness()
    set_widget_window_chrome_provider(set_dark_title_bar)

    # CLI mode
    if args:
        cli = BookmarkCLI()
        rc = cli.run(args)
        raise SystemExit(rc if isinstance(rc, int) else 0)

    # GUI mode with error handling
    try:
        root = tk.Tk()
        root.withdraw()  # Hide while checking dependencies

        # Configure DPI scaling BEFORE style init so sizes are correct
        _configure_tk_scaling(root)

        # Initialize style manager
        style_manager.initialize(root)

        # Confirm the generated bootstrap contract still resolves before UI construction.
        dep_ok = check_and_install_dependencies(root)
        if not dep_ok:
            log.warning("Dependency repair is required before launch")
            root.destroy()
            return

        # Bind desktop dependencies after the non-importing bootstrap check.
        import_dependencies()

        root.deiconify()  # Show window

        _show_first_run_privacy_notice(root)

        from bookmark_organizer_pro.app import FinalBookmarkOrganizerApp

        FinalBookmarkOrganizerApp(root)
        root.mainloop()

    except Exception as e:
        log.exception("Fatal error in main")
        # Try to show error dialog
        try:
            messagebox.showerror(
                "Fatal Error",
                f"An unexpected error occurred:\n\n{str(e)[:500]}\n\n"
                f"Please check the log file at:\n{LOG_FILE}"
            )
        except Exception:
            print(f"FATAL ERROR: {e}")
        raise
