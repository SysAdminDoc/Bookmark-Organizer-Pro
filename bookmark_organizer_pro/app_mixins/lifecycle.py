"""Application lifecycle and status actions for the app coordinator."""

from __future__ import annotations

import tkinter as tk

from bookmark_organizer_pro.i18n import _, format_message, format_plural
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.services.auto_snapshot import SnapshotScheduler
from bookmark_organizer_pro.services.settings_store import load_settings, update_settings
from bookmark_organizer_pro.services.snapshot import SnapshotArchiver
from bookmark_organizer_pro.ui.foundation import pluralize


class LifecycleActionsMixin:
    """Startup data load, status bar, polling, undo/redo, and close handlers."""

    def _load_and_display_data(self):
        """Load bookmarks and display - non-blocking"""
        self._refresh_category_list()
        self._refresh_bookmark_list()
        self._refresh_analytics()

        recovery_required = self.bookmark_manager.recovery_required
        if not recovery_required:
            # Capture a startup safepoint in the background so the pre-session state
            # is always recoverable (deletes are immediate / unconfirmed by design).
            import threading
            threading.Thread(
                target=lambda: self.bookmark_manager.create_safepoint("startup"),
                daemon=True,
            ).start()

        # Queue favicon downloads
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        self.favicon_manager.queue_bookmarks(bookmarks)

        if recovery_required:
            self._set_status(self.bookmark_manager.recovery_message)
            if hasattr(self, "_show_toast"):
                self._show_toast(
                    "Library writes are blocked. Use Tools > Restore from Backup, "
                    "or salvage recoverable records there.",
                    "error",
                )
        elif bookmarks:
            self._set_status(format_plural(
                "Loaded {count} bookmark", "Loaded {count} bookmarks",
                len(bookmarks), count=len(bookmarks),
            ))
        else:
            self._set_status("Library ready")

        self._start_dead_link_scheduler()
        self._start_snapshot_scheduler()

    def _post_to_ui(self, callback):
        """Enqueue a callback for the main-thread dispatcher without touching Tk."""
        if getattr(self, "_closing", False):
            return False
        dispatcher = getattr(self, "ui_dispatcher", None)
        return bool(dispatcher and dispatcher.post(callback))

    def _undo(self):
        """Undo"""
        if self.command_stack.undo():
            self._refresh_all()
    
    def _redo(self):
        """Redo"""
        if self.command_stack.redo():
            self._refresh_all()
    
    def _refresh_all(self):
        """Refresh all displays"""
        self._refresh_category_list()
        self._refresh_bookmark_list()
        self._refresh_analytics()
        if hasattr(self, "_refresh_read_later_sidebar"):
            try:
                self._refresh_read_later_sidebar()
            except Exception:
                pass
        if hasattr(self, "_refresh_flows_sidebar"):
            try:
                self._refresh_flows_sidebar()
            except Exception:
                pass
    
    def _set_status(self, message: str):
        """Set status message and update counts"""
        if self.status_label:
            try:
                self.status_label.configure(text=_(message))
            except Exception:
                pass
        # Update counts whenever status changes
        self._update_status_counts()
    
    def _show_status_progress(self, show: bool = True):
        """Show or hide progress indicator in status bar"""
        if hasattr(self, 'status_progress'):
            try:
                if show:
                    self.status_progress.pack(side=tk.LEFT, padx=(8, 0))
                    self.status_progress.start(10)
                else:
                    self.status_progress.stop()
                    self.status_progress.pack_forget()
            except Exception:
                pass
    
    def _update_status_counts(self):
        """Update item counts in status bar"""
        try:
            if hasattr(self, 'status_total_label') and self.status_total_label:
                total = len(self.bookmark_manager.get_all_bookmarks())
                self.status_total_label.configure(text=pluralize(total, "bookmark"))
            
            if hasattr(self, 'status_selected_label') and self.status_selected_label:
                selected = len(self.selected_bookmarks) if hasattr(self, 'selected_bookmarks') else 0
                if selected > 0:
                    self.status_selected_label.configure(text=format_message('{value_0} selected', value_0=selected))
                else:
                    self.status_selected_label.configure(text="")
        except Exception:
            pass
    
    def _try_enable_window_dnd(self):
        """Drag-drop requires tkinterdnd2 which may not be installed"""
        # Native drag-drop requires tkinterdnd2
        # Users can still use the browse button or import menu
        pass
    
    def _start_analytics_polling(self):
        """Start periodic analytics refresh"""
        self._analytics_poll_id = None
        self._poll_analytics()
    
    def _poll_analytics(self):
        """Poll and refresh analytics periodically"""
        if getattr(self, "_closing", False):
            return
        try:
            self._refresh_analytics()
        except Exception:
            log.warning("Analytics poll failed", exc_info=True)

        # Schedule next poll (30 seconds) unless the app is shutting down.
        if not getattr(self, "_closing", False):
            self._analytics_poll_id = self.root.after(30000, self._poll_analytics)

    def _cycle_focus_section(self):
        """Cycle keyboard focus between search, sidebar, and bookmark list (F6)."""
        targets = []
        if hasattr(self, "search_entry") and self.search_entry:
            targets.append(self.search_entry)
        if hasattr(self, "filter_buttons"):
            first_filter = list(self.filter_buttons.values())
            if first_filter:
                targets.append(first_filter[0])
        if hasattr(self, "tree") and self.tree:
            targets.append(self.tree)
        if hasattr(self, "chat_panel") and self.chat_panel:
            targets.append(self.chat_panel._entry)
        if not targets:
            return "break"
        try:
            current = self.root.focus_get()
            idx = -1
            for i, t in enumerate(targets):
                if current is t or (hasattr(current, "master") and current.master is t):
                    idx = i
                    break
            next_idx = (idx + 1) % len(targets)
            targets[next_idx].focus_set()
        except Exception:
            if targets:
                targets[0].focus_set()
        return "break"

    def _start_dead_link_scheduler(self):
        """Start periodic dead-link scanning if enabled in settings."""
        try:
            interval = int(load_settings().get("dead_link_scan_interval_hours", 0))
        except (OSError, TypeError, ValueError):
            interval = 0
        if interval <= 0:
            return
        try:
            from bookmark_organizer_pro.services.dead_link_scanner import DeadLinkScanner
            self._dead_link_scanner = DeadLinkScanner(
                get_bookmarks=self.bookmark_manager.get_all_bookmarks,
            )
            self._dead_link_scanner.start(interval_hours=interval)
            log.info(f"Dead-link scanner started (interval: {interval}h)")
        except Exception:
            log.debug("Failed to start dead-link scanner", exc_info=True)

    def _start_snapshot_scheduler(self):
        """Restore scheduled snapshots once, after bookmarks are loaded."""
        if getattr(self, "_snapshot_scheduler", None) is not None:
            return self._snapshot_scheduler
        try:
            settings = load_settings()
            interval = int(settings.get("auto_snapshot_interval_hours", 24))
        except Exception:
            settings = {}
            interval = 24

        try:
            archiver = SnapshotArchiver()
            scheduler = SnapshotScheduler(
                self._capture_scheduled_snapshot,
                self.bookmark_manager.get_bookmark,
                interval_hours=interval,
                failure_store=archiver.failure_store,
            )
            enabled = bool(settings.get("auto_snapshot_enabled", False))
            if scheduler.interval_hours != interval:
                scheduler.set_interval(interval)
            if scheduler.enabled != enabled:
                scheduler.set_enabled(enabled)
            self._snapshot_archiver = archiver
            self._snapshot_scheduler = scheduler
            if enabled:
                scheduler.start()
                log.info(
                    "Restored auto-snapshot scheduler (%sh, %s bookmarks)",
                    scheduler.interval_hours,
                    len(scheduler.list_scheduled()),
                )
            return scheduler
        except Exception:
            log.warning("Failed to restore auto-snapshot scheduler", exc_info=True)
            return None

    def _capture_scheduled_snapshot(self, bookmark):
        """Capture one scheduled bookmark and persist the updated bookmark state."""
        archiver = getattr(self, "_snapshot_archiver", None)
        if archiver is None:
            archiver = SnapshotArchiver()
            self._snapshot_archiver = archiver
        ok, detail = archiver.snapshot(bookmark)
        if ok:
            self.bookmark_manager.save_bookmarks()
            self._post_to_ui(self._refresh_all)
        return ok, detail

    def _ensure_snapshot_scheduler(self):
        scheduler = getattr(self, "_snapshot_scheduler", None)
        return scheduler or self._start_snapshot_scheduler()

    def _set_snapshot_schedule_preferences(self, enabled: bool, interval_hours: int) -> bool:
        """Persist scheduler preferences and apply them to the one live instance."""
        try:
            interval = max(1, min(24 * 30, int(interval_hours)))
            update_settings({
                "auto_snapshot_enabled": bool(enabled),
                "auto_snapshot_interval_hours": interval,
            })
            scheduler = self._ensure_snapshot_scheduler()
            if scheduler is None:
                raise RuntimeError("snapshot scheduler could not be initialized")
            scheduler.set_interval(interval)
            scheduler.set_enabled(bool(enabled))
            if enabled:
                scheduler.start()
            else:
                scheduler.stop()
            return True
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            log.warning("Could not update scheduled snapshot settings: %s", exc)
            self._set_status(format_message(
                "Scheduled snapshots were not updated: {error}", error=str(exc)[:160],
            ))
            self._show_toast(
                "Scheduled snapshot settings could not be saved", "error",
            )
            return False

    def _on_close(self):
        """Handle close — stop timers and background work before tearing down."""
        self._closing = True

        for attr in ("_analytics_poll_id", "_grid_after_id", "_search_after"):
            after_id = getattr(self, attr, None)
            if after_id:
                try:
                    self.root.after_cancel(after_id)
                except Exception:
                    pass

        scanner = getattr(self, "_dead_link_scanner", None)
        if scanner is not None:
            try:
                scanner.stop()
            except Exception:
                log.debug("Error stopping dead-link scanner", exc_info=True)

        snapshot_scheduler = getattr(self, "_snapshot_scheduler", None)
        if snapshot_scheduler is not None:
            try:
                snapshot_scheduler.stop()
            except Exception:
                log.debug("Error stopping auto-snapshot scheduler", exc_info=True)

        bookmark_manager = getattr(self, "bookmark_manager", None)
        if bookmark_manager is not None:
            bookmark_manager.stop_file_watcher()

        for manager in (getattr(self, "favicon_manager", None),
                        getattr(self, "task_runner", None)):
            if manager is not None:
                try:
                    manager.shutdown()
                except Exception:
                    log.debug("Error during shutdown", exc_info=True)

        dispatcher = getattr(self, "ui_dispatcher", None)
        if dispatcher is not None:
            dispatcher.shutdown()

        callback = getattr(self, "_theme_change_callback", None)
        if callback is not None:
            try:
                self.theme_manager.remove_theme_change_callback(callback)
            except Exception:
                log.debug("Error removing theme callback", exc_info=True)

        try:
            self.root.destroy()
        except Exception:
            pass
