"""Desktop launcher entry point for Bookmark Organizer Pro."""

from __future__ import annotations

import multiprocessing
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
from bookmark_organizer_pro.ui import check_and_install_dependencies
from bookmark_organizer_pro.ui.style_manager import style_manager
from bookmark_organizer_pro.ui.widgets import set_widget_window_chrome_provider


def _show_first_run_privacy_notice(root: tk.Tk):
    """Show a one-time privacy notice on first launch."""
    import json
    from bookmark_organizer_pro.constants import SETTINGS_FILE
    try:
        if SETTINGS_FILE.exists():
            settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if settings.get("privacy_notice_shown"):
                return
        else:
            settings = {}
    except Exception:
        settings = {}

    messagebox.showinfo(
        "Privacy Notice",
        "Bookmark Organizer Pro is fully local.\n\n"
        "No data leaves your machine unless you explicitly\n"
        "configure an AI provider API key in Settings > AI.\n\n"
        "All bookmarks, snapshots, and search indexes\n"
        "are stored in ~/.bookmark_organizer/.",
        parent=root,
    )

    settings["privacy_notice_shown"] = True
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        pass


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

    if IS_WINDOWS:
        multiprocessing.freeze_support()
    setup_dpi_awareness()
    set_widget_window_chrome_provider(set_dark_title_bar)

    # CLI mode
    if args:
        cli = BookmarkCLI()
        cli.run(args)
        return

    # GUI mode with error handling
    try:
        root = tk.Tk()
        root.withdraw()  # Hide while checking dependencies

        # Initialize style manager
        style_manager.initialize(root)

        # Check and install dependencies
        dep_ok = check_and_install_dependencies(root)
        if not dep_ok:
            log.warning("User cancelled dependency installation")
            root.destroy()
            return

        # Import dependencies after check
        import_dependencies()

        # Configure DPI scaling for tk
        _configure_tk_scaling(root)

        root.deiconify()  # Show window

        _show_first_run_privacy_notice(root)

        from bookmark_organizer_pro.app import FinalBookmarkOrganizerApp

        app = FinalBookmarkOrganizerApp(root)
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
