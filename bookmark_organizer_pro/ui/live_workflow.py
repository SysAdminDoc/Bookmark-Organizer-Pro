"""Reusable live-activity dialog for long-running AI batch workflows.

The AI categorization / tagging / summary workflows all share the same shape: a
Toplevel with a header (title + running count), a thin progress bar, a scrolling
activity feed, and a footer (status text + Stop/Done). This module factors that
scaffolding into one widget so the three workflows stay in sync and the
memory-safety guarantees live in a single place.

Two behaviours are baked in deliberately:

* **Bounded feed** — only the most recent ``MAX_FEED_ROWS`` rows stay mounted.
  Without this, a large run mounts one Frame + several Labels per bookmark and
  never frees them, leaking memory for the life of the dialog. The feed
  auto-scrolls, so older rows are never on screen anyway.

* **Staggered reveal ("drip")** — providers return a whole batch (e.g. 50
  bookmarks) in a single API call, which previously made the feed jump 0 -> 50
  and then sit still while the next batch was fetched. Workers instead *enqueue*
  rendered rows and the dialog reveals them one at a time on a timer, so the run
  looks like it is processing bookmark-by-bookmark. This decouples API batch
  arrival from the visual reveal and makes the experience feel faster and
  smoother. The reveal rate adapts: a single batch drips one-by-one, but if
  several batches pile up the dialog accelerates so it never lags far behind.
"""

from __future__ import annotations

import tkinter as tk
from collections import deque
from typing import Callable, Optional

from bookmark_organizer_pro.ui.components import ScrollableFrame
from bookmark_organizer_pro.ui.foundation import FONTS
from bookmark_organizer_pro.ui.widgets import ModernButton, apply_window_chrome, get_theme

# Keep only the most recent rows mounted (see module docstring).
MAX_FEED_ROWS = 200

# Milliseconds between reveals when dripping one row at a time.
DEFAULT_REVEAL_MS = 45

# Backlog above which the reveal accelerates to catch up (multiple batches
# queued). At or below this, rows drip strictly one at a time.
_DRIP_THRESHOLD = 60

# Hard ceiling on queued-but-unrevealed rows. A pathologically fast provider
# cannot balloon memory; overflow rows are dropped (they would be trimmed from
# the visible feed anyway) but still counted toward progress.
_MAX_PENDING = MAX_FEED_ROWS * 6


# status -> (glyph, theme color attribute) for the standard row builder.
_STATUS_GLYPHS = {
    "ok": ("✓", "accent_success"),
    "warn": ("~", "accent_warning"),
    "skip": ("–", "text_muted"),
    "none": ("–", "text_muted"),
    "error": ("⚠", "accent_warning"),
}


class LiveWorkflowDialog:
    """A modal live-activity dialog driven by a background worker thread.

    Typical use::

        dialog = LiveWorkflowDialog(self.root, title="AI Categorization",
                                    total=len(bookmarks))

        def worker():
            for ... in ...:
                if dialog.cancelled:
                    break
                dialog.set_status("Processing 1–50 …")
                dialog.add_result(status="ok", title=bm.title, detail="...")
            dialog.signal_finish("Done — 50 categorized")

        dialog.run(worker)

    Thread model: ``add_result`` / ``add_entry`` / ``set_status`` /
    ``signal_finish`` are safe to call from the worker thread. Row reveal and
    all widget mutation happen on the Tk main thread via the reveal pump.
    """

    def __init__(self, parent, *, title: str, total: int,
                 width: int = 700, height: int = 560,
                 reveal_ms: int = DEFAULT_REVEAL_MS,
                 max_feed_rows: int = MAX_FEED_ROWS,
                 on_cancel: Optional[Callable[[], None]] = None):
        self.parent = parent
        self.total = max(0, int(total))
        self.reveal_ms = max(0, int(reveal_ms))
        self.max_feed_rows = max(10, int(max_feed_rows))
        self._on_cancel = on_cancel

        self.cancelled = False
        self._revealed = 0
        self._queue: "deque[Callable]" = deque()
        self._finished = False
        self._finish_summary: Optional[str] = None

        theme = get_theme()
        self.theme = theme

        dialog = tk.Toplevel(parent)
        dialog.title(f"{title} — Live")
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry(f"{width}x{height}")
        dialog.minsize(int(width * 0.85), int(height * 0.78))
        dialog.transient(parent)
        dialog.grab_set()
        apply_window_chrome(dialog)
        self.dialog = dialog

        dialog.update_idletasks()
        try:
            x = parent.winfo_x() + (parent.winfo_width() - width) // 2
            y = parent.winfo_y() + (parent.winfo_height() - height) // 2
            dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        # ── Header ──
        header = tk.Frame(dialog, bg=theme.bg_secondary, padx=20, pady=12)
        header.pack(fill=tk.X)
        tk.Label(
            header, text=title, bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.subtitle(bold=True),
        ).pack(side=tk.LEFT)
        self.stats_label = tk.Label(
            header, text=f"0 / {self.total}", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.body(),
        )
        self.stats_label.pack(side=tk.RIGHT)

        # ── Progress bar ──
        bar_bg = tk.Frame(dialog, bg=theme.bg_tertiary, height=4)
        bar_bg.pack(fill=tk.X)
        self.bar_fill = tk.Frame(bar_bg, bg=theme.accent_primary, height=4)
        self.bar_fill.place(x=0, y=0, relheight=1.0, relwidth=0)

        # ── Live activity feed (scrollable, bounded) ──
        self.feed_frame = ScrollableFrame(dialog, bg=theme.bg_primary)
        self.feed_frame.pack(fill=tk.BOTH, expand=True)
        self.feed = self.feed_frame.inner

        # ── Footer ──
        footer = tk.Frame(dialog, bg=theme.bg_secondary, padx=16, pady=10)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_label = tk.Label(
            footer, text="Starting…", bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.small(),
        )
        self.status_label.pack(side=tk.LEFT)

        self.cancel_btn = ModernButton(footer, text="Stop", command=self._cancel, padx=14, pady=5)
        self.cancel_btn.pack(side=tk.RIGHT)
        self.done_btn = ModernButton(footer, text="Done", style="success", padx=14, pady=5,
                                     command=self.close)  # shown only when complete

        dialog.protocol("WM_DELETE_WINDOW", self._on_close_request)

    # ── Lifecycle ────────────────────────────────────────────────────────
    def run(self, worker: Callable[[], None]):
        """Start the reveal pump and launch ``worker`` on a daemon thread."""
        import threading
        self._schedule_pump()
        threading.Thread(target=self._guarded_worker, args=(worker,), daemon=True).start()

    def _guarded_worker(self, worker: Callable[[], None]):
        try:
            worker()
        except Exception:  # pragma: no cover - defensive; worker logs its own errors
            from bookmark_organizer_pro.logging_config import log
            log.warning("Live workflow worker crashed", exc_info=True)
            self.signal_finish("Stopped — an unexpected error occurred")

    def _alive(self) -> bool:
        try:
            return bool(self.dialog.winfo_exists())
        except Exception:
            return False

    def _cancel(self):
        if self.cancelled:
            return
        self.cancelled = True
        try:
            self.cancel_btn.set_state("disabled")
            self.cancel_btn.set_text("Stopping…")
        except Exception:
            pass
        if self._on_cancel:
            try:
                self._on_cancel()
            except Exception:
                pass

    def _on_close_request(self):
        """Window-manager close (the X): stop any in-flight work, then close."""
        if not self._finished:
            self._cancel()
        self.close()

    def close(self):
        try:
            self.dialog.grab_release()
        except Exception:
            pass
        try:
            self.dialog.destroy()
        except Exception:
            pass

    # ── Worker-facing API (thread-safe) ──────────────────────────────────
    def set_status(self, text: str):
        """Update the footer status line (safe from the worker thread)."""
        try:
            self.parent.after(0, self._apply_status, text)
        except Exception:
            pass

    def _apply_status(self, text: str):
        if self._alive():
            try:
                self.status_label.configure(text=text)
            except Exception:
                pass

    def add_entry(self, render_fn: Callable[[tk.Widget, object], None]):
        """Queue a custom row. ``render_fn(feed_parent, theme)`` packs one row.

        Safe to call from the worker thread. The row is revealed later by the
        pump, one at a time, for the drip effect.
        """
        self._queue.append(render_fn)
        overflow = len(self._queue) - _MAX_PENDING
        while overflow > 0:
            try:
                self._queue.popleft()
                self._revealed += 1  # keep progress honest for dropped rows
            except IndexError:
                break
            overflow -= 1

    def add_result(self, *, status: str, title: str, detail: str = "",
                   detail_color: Optional[str] = None):
        """Queue a standard two-line activity row (dot + title + detail)."""
        self.add_entry(lambda feed, theme: self._build_standard_row(
            feed, theme, status, title, detail, detail_color))

    def signal_finish(self, summary: str):
        """Mark the run complete. The dialog flips to "Done" only after every
        queued row has been revealed, so the drip animation always finishes."""
        self._finish_summary = summary
        self._finished = True

    # ── Reveal pump (runs on the Tk main thread) ─────────────────────────
    def _schedule_pump(self):
        if not self._alive():
            return
        try:
            self.dialog.after(max(1, self.reveal_ms), self._pump)
        except Exception:
            pass

    def _pump(self):
        if not self._alive():
            return

        backlog = len(self._queue)
        if self.cancelled:
            per_tick = backlog or 1        # flush quickly on cancel
        elif backlog <= _DRIP_THRESHOLD:
            per_tick = 1                   # strict one-at-a-time drip
        else:
            per_tick = max(1, backlog // 30)  # catch up when batches pile up

        for _ in range(per_tick):
            if not self._queue:
                break
            render_fn = self._queue.popleft()
            self._reveal_one(render_fn)

        if self._finished and not self._queue:
            self._apply_finish()
            return
        self._schedule_pump()

    def _reveal_one(self, render_fn: Callable[[tk.Widget, object], None]):
        try:
            render_fn(self.feed, self.theme)
        except Exception:
            pass
        self._trim_feed()
        self._revealed += 1
        try:
            self.stats_label.configure(text=f"{self._revealed} / {self.total}")
            if self.total:
                self.bar_fill.place(relwidth=min(1.0, self._revealed / self.total))
            self.feed_frame.canvas.update_idletasks()
            self.feed_frame.canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _trim_feed(self):
        try:
            children = self.feed.winfo_children()
            if len(children) > self.max_feed_rows:
                for old in children[:-self.max_feed_rows]:
                    old.destroy()
        except Exception:
            pass

    def _apply_finish(self):
        if not self._alive():
            return
        try:
            self.bar_fill.configure(bg=self.theme.accent_success)
            self.bar_fill.place(relwidth=1.0)
            # Reconcile the counter in case any overflow rows were dropped.
            self.stats_label.configure(text=f"{self.total} / {self.total}")
            self.cancel_btn.pack_forget()
            self.done_btn.pack(side=tk.RIGHT)
            if self._finish_summary:
                self.status_label.configure(text=self._finish_summary,
                                            fg=self.theme.text_primary)
        except Exception:
            pass

    # ── Standard row builder ─────────────────────────────────────────────
    def _build_standard_row(self, feed, theme, status, title, detail, detail_color):
        glyph, color_attr = _STATUS_GLYPHS.get(status, _STATUS_GLYPHS["none"])
        dot_color = getattr(theme, color_attr, theme.text_muted)

        row = tk.Frame(feed, bg=theme.bg_primary, padx=12, pady=5)
        row.pack(fill=tk.X, pady=1)

        tk.Label(
            row, text=glyph, bg=theme.bg_primary, fg=dot_color,
            font=FONTS.body(bold=True), width=2,
        ).pack(side=tk.LEFT, padx=(0, 6))

        info = tk.Frame(row, bg=theme.bg_primary)
        info.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(
            info, text=(title or "")[:60], bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.body(), anchor="w",
        ).pack(anchor="w")

        if detail:
            tk.Label(
                info, text=detail, bg=theme.bg_primary,
                fg=detail_color or theme.text_muted, font=FONTS.small(), anchor="w",
            ).pack(anchor="w")
