"""Selection, opening, and context-menu actions for the app coordinator."""

from __future__ import annotations

import tkinter as tk
from tkinter import simpledialog
import threading
import webbrowser
from datetime import datetime

from bookmark_organizer_pro.i18n import _, format_message, format_plural
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.snapshot import open_snapshot_file
from bookmark_organizer_pro.ui.widgets import get_theme
from bookmark_organizer_pro.utils.runtime import open_external_url


def _open_external_url(url: str) -> bool:
    """Open external URLs through the shared runtime helper."""
    return open_external_url(url, opener=webbrowser.open)


class SelectionActionsMixin:
    """Selection state, bookmark opening, and row context-menu behavior."""

    def _select_all_bookmarks(self):
        """Select all bookmarks in view (Ctrl+A)"""
        all_items = self.tree.get_children()
        self.tree.selection_set(all_items)
        self.selected_bookmarks = [int(item) for item in all_items]
        self._update_selection_bar()
        if hasattr(self, "_update_right_rail_selection"):
            self._update_right_rail_selection()
        if hasattr(self, "_refresh_table_semantic_status"):
            self._refresh_table_semantic_status()
        self._set_status(format_message("Selected {count} bookmarks", count=len(all_items)))
        return "break"  # Prevent default behavior

    def _on_selection_change(self, event):
        """Handle tree selection change"""
        self.selected_bookmarks = [int(item) for item in self.tree.selection()]
        self._update_status_counts()
        self._update_selection_bar()
        if hasattr(self, "_update_right_rail_selection"):
            self._update_right_rail_selection()
        if hasattr(self, "_refresh_table_semantic_status"):
            self._refresh_table_semantic_status()
        if self.selected_bookmarks:
            self._set_status(format_plural(
                "{count} bookmark selected", "{count} bookmarks selected",
                len(self.selected_bookmarks), count=len(self.selected_bookmarks),
            ))
    
    def _on_item_double_click(self, event):
        """Handle double-click"""
        item = self.tree.identify_row(event.y)
        if item:
            bookmark = self.bookmark_manager.get_bookmark(int(item))
            if bookmark:
                self._open_bookmark(bookmark)
    
    def _on_bookmark_click(self, bookmark: Bookmark):
        """Handle bookmark click"""
        pass
    
    def _open_bookmark(self, bookmark: Bookmark):
        """Open bookmark in browser"""
        if _open_external_url(bookmark.url):
            bookmark.visit_count += 1
            bookmark.last_visited = datetime.now().isoformat()
            self.bookmark_manager.update_bookmark(bookmark)

    def _open_offline_copy(self, bookmark: Bookmark):
        """Verify and open a selected bookmark's local snapshot."""
        opened, detail = open_snapshot_file(bookmark)
        if opened:
            self._set_status(
                _("Opened offline copy for {title}").format(
                    title=bookmark.title[:60],
                )
            )
            return
        self._set_status(detail)
        if hasattr(self, "_toast"):
            self._toast(detail, "error")

    def _show_context_menu(self, event=None):
        """Show the row action/sort menu for pointer or keyboard invocation."""
        theme = get_theme()
        item = ""
        if event is not None and getattr(event, "num", None) == 3:
            item = self.tree.identify_row(event.y)
        if not item:
            selected = self.tree.selection()
            item = str(selected[0]) if selected else str(self.tree.focus() or "")
        if not item:
            return "break"
        
        # Select item if not already selected
        if item not in self.tree.selection():
            self.tree.selection_set(item)
        
        # Update selected_bookmarks list
        self.selected_bookmarks = [int(i) for i in self.tree.selection()]
        self._update_selection_bar()
        if hasattr(self, "_update_right_rail_selection"):
            self._update_right_rail_selection()
        
        # Get selected bookmark for domain search
        first_bookmark = None
        if self.selected_bookmarks:
            first_bookmark = self.bookmark_manager.get_bookmark(self.selected_bookmarks[0])
        
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                      activebackground=theme.bg_hover, activeforeground=theme.text_primary)
        menu.add_command(label=_("Open in Browser"), command=self._open_selected)
        if first_bookmark and first_bookmark.snapshot_path:
            menu.add_command(
                label=_("Open Offline Copy"),
                command=lambda: self._open_offline_copy(first_bookmark),
            )
        menu.add_command(label=_("Reader View"), command=self._open_reader_view)
        selected_bookmarks = [
            self.bookmark_manager.get_bookmark(bookmark_id)
            for bookmark_id in self.selected_bookmarks
        ]
        youtube_bookmarks = [
            bookmark
            for bookmark in selected_bookmarks
            if bookmark is not None
            and self._is_youtube_bookmark(bookmark)
        ]
        if youtube_bookmarks:
            menu.add_command(
                label=_("Fetch YouTube Transcript…"),
                command=self._fetch_youtube_transcripts,
            )
        if any(getattr(bookmark, "youtube_transcript_path", "") for bookmark in youtube_bookmarks):
            menu.add_command(
                label=_("Remove YouTube Transcript"),
                command=self._remove_youtube_transcripts,
            )
        menu.add_command(label=_("Edit Bookmark"), command=self._edit_selected)
        menu.add_separator()

        sort_menu = tk.Menu(
            menu,
            tearoff=0,
            bg=theme.bg_secondary,
            fg=theme.text_primary,
            activebackground=theme.bg_hover,
            activeforeground=theme.text_primary,
        )
        for label, column in (
            (_("Site"), "#0"),
            (_("Title"), "title"),
            (_("Collection / Tags"), "organization"),
            (_("Saved"), "saved"),
            (_("Status"), "status"),
            (_("Pinned"), "favorite"),
        ):
            sort_menu.add_command(
                label=label,
                command=lambda value=column: self.tree.sort_by_column(value),
            )
        menu.add_cascade(label=_("Sort by"), menu=sort_menu)
        menu.add_separator()
        
        # Search Domain option
        if first_bookmark and first_bookmark.domain:
            menu.add_command(
                label=format_message('Filter by Domain ({value_0})', value_0=first_bookmark.domain),
                command=lambda: self._filter_by_domain(first_bookmark.domain)
            )
        
        # Send To submenu with all categories
        send_to_menu = tk.Menu(menu, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                              activebackground=theme.bg_hover, activeforeground=theme.text_primary)
        
        categories = self.category_manager.get_sorted_categories()
        for cat in categories:
            send_to_menu.add_command(
                label=cat,
                command=lambda c=cat: self._send_to_category(c)
            )
        
        menu.add_cascade(label=_("Move to Category"), menu=send_to_menu)
        menu.add_separator()
        menu.add_command(label=_("Copy URL"), command=self._copy_url)
        menu.add_command(label=_("Toggle Pin"), command=self._toggle_pin)
        menu.add_command(label=_("Set Custom Favicon…"), command=self._show_custom_favicon_dialog)
        menu.add_separator()
        
        # AI Tools submenu
        ai_menu = tk.Menu(menu, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                         activebackground=theme.bg_hover, activeforeground=theme.text_primary)
        ai_menu.add_command(label=_("AI Categorize"), command=self._ai_categorize)
        ai_menu.add_command(label=_("Suggest Tags"), command=self._ai_suggest_tags)
        ai_menu.add_command(label=_("Summarize"), command=self._ai_summarize)
        ai_menu.add_command(label=_("Improve Titles"), command=self._ai_improve_titles)
        menu.add_cascade(label=_("Assistant Tools"), menu=ai_menu)

        menu.add_separator()
        menu.add_command(label=_("Mark as Needs Review"), command=self._mark_as_broken)
        menu.add_command(label=_("Delete"), command=self._delete_selected)

        if event is not None and getattr(event, "num", None) == 3:
            x_root, y_root = event.x_root, event.y_root
        else:
            x_root = self.tree.winfo_rootx() + 48
            y_root = self.tree.winfo_rooty() + 72
        menu.tk_popup(x_root, y_root)
        return "break"

    @staticmethod
    def _is_youtube_bookmark(bookmark: Bookmark) -> bool:
        from bookmark_organizer_pro.services.youtube_transcript import is_youtube_url

        return is_youtube_url(bookmark.url)

    def _youtube_transcript_action(self, *, remove: bool = False) -> None:
        bookmarks = [
            self.bookmark_manager.get_bookmark(bookmark_id)
            for bookmark_id in (getattr(self, "selected_bookmarks", []) or [])
        ]
        if remove:
            targets = [
                bookmark
                for bookmark in bookmarks
                if bookmark is not None and getattr(bookmark, "youtube_transcript_path", "")
            ]
        else:
            targets = [
                bookmark
                for bookmark in bookmarks
                if bookmark is not None and self._is_youtube_bookmark(bookmark)
            ]
        if not targets:
            self._show_toast(
                _("Select an eligible YouTube bookmark first."),
                "info",
            )
            return

        language = "en"
        if not remove:
            language = simpledialog.askstring(
                _("YouTube Transcript"),
                _("Subtitle language (for example, en or pt-BR):"),
                initialvalue="en",
                parent=self.root,
            )
            if language is None:
                return
            language = language.strip()
            if not language:
                self._show_toast(_("Enter a subtitle language."), "error")
                return

        action = _("Removing") if remove else _("Fetching")
        self._set_status(format_plural(
            "{action} {count} YouTube transcript…",
            "{action} {count} YouTube transcripts…",
            len(targets),
            action=action,
            count=len(targets),
        ))

        def worker() -> None:
            from bookmark_organizer_pro.services.youtube_transcript import YouTubeTranscriptService

            service = YouTubeTranscriptService()
            succeeded = 0
            failed = 0
            changed = False
            for bookmark in targets:
                result = (
                    service.remove(bookmark)
                    if remove
                    else service.capture(bookmark, language=language)
                )
                if result.success:
                    if not remove:
                        changed = service.apply(bookmark, result) or changed
                    succeeded += 1
                else:
                    failed += 1
            if changed or (remove and succeeded):
                self.bookmark_manager.save_bookmarks()
            self._post_to_ui(
                lambda: self._finish_youtube_transcripts(
                    succeeded, failed, remove,
                )
            )

        threading.Thread(target=worker, daemon=True).start()

    def _fetch_youtube_transcripts(self) -> None:
        self._youtube_transcript_action(remove=False)

    def _remove_youtube_transcripts(self) -> None:
        self._youtube_transcript_action(remove=True)

    def _finish_youtube_transcripts(self, succeeded: int, failed: int, remove: bool) -> None:
        verb = _("Removed") if remove else _("Fetched")
        message = format_plural(
            "{verb} {count} YouTube transcript",
            "{verb} {count} YouTube transcripts",
            succeeded,
            verb=verb,
            count=succeeded,
        )
        if failed:
            message += " " + format_message("{count} failed.", count=failed)
        self._set_status(message)
        self._toast(message, "error" if failed else "success")
        if succeeded:
            self._refresh_all()
    
    def _send_to_category(self, category: str):
        """Send selected bookmarks to a category"""
        if not self.selected_bookmarks:
            return
        
        count = 0
        for bm_id in self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            if bookmark:
                bookmark.category = category
                self.bookmark_manager.update_bookmark(bookmark)
                count += 1
        
        self._refresh_all()
        self._set_status(format_plural(
            "Moved {count} bookmark to '{category}'",
            "Moved {count} bookmarks to '{category}'",
            count,
            count=count,
            category=category,
        ))
    
    def _mark_as_broken(self):
        """Mark selected bookmarks as broken"""
        if not self.selected_bookmarks:
            return
        
        for bm_id in self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            if bookmark:
                bookmark.is_valid = False
                bookmark.notes = (bookmark.notes or "") + "\n[Marked as potentially broken]"
                self.bookmark_manager.update_bookmark(bookmark)
        
        self._refresh_bookmark_list()
        self._set_status(format_plural(
            "Marked {count} bookmark as broken",
            "Marked {count} bookmarks as broken",
            len(self.selected_bookmarks),
            count=len(self.selected_bookmarks),
        ))
