"""Desktop launcher entry point for Bookmark Organizer Pro."""

from __future__ import annotations

import multiprocessing
import sys
import tkinter as tk
from tkinter import messagebox
from typing import Sequence

from bookmark_organizer_pro.cli import BookmarkCLI
from bookmark_organizer_pro.constants import IS_WINDOWS, LOG_FILE
from bookmark_organizer_pro.desktop_bootstrap import (
    import_dependencies,
    set_dark_title_bar,
    setup_dpi_awareness,
)
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.ui import check_and_install_dependencies
from bookmark_organizer_pro.ui.style_manager import style_manager
from bookmark_organizer_pro.ui.widgets import set_widget_window_chrome_provider


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
