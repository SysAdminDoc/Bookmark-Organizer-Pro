"""Bookmark editor dialog."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import Callable, List

from bookmark_organizer_pro.i18n import _, format_message
from bookmark_organizer_pro.managers import TagManager
from bookmark_organizer_pro.models import Bookmark

from .foundation import FONTS, DesignTokens, readable_text_on
from .tk_interactions import bind_scoped_mousewheel, make_keyboard_activatable
from .widget_controls import ModernButton, TagEditor, ThemedWidget
from .widget_runtime import _open_external_url, apply_window_chrome, get_theme
from .window_geometry import apply_screen_aware_geometry


# =============================================================================
# Bookmark Editor Dialog
# =============================================================================
class BookmarkEditorDialog(tk.Toplevel, ThemedWidget):
    """Dialog for editing a single bookmark's fields."""
    
    def __init__(self, parent, bookmark: Bookmark = None, 
                 categories: List[str] = None, tag_manager: TagManager = None,
                 available_tags: List[str] = None, on_save: Callable = None):
        super().__init__(parent)
        self.bookmark = bookmark
        self.categories = categories or []
        self.tag_manager = tag_manager
        self.available_tags = available_tags or (list(tag_manager.tags.keys()) if tag_manager else [])
        self.on_save = on_save
        self.result = None
        
        theme = get_theme()
        
        self.title(_("Edit Bookmark") if bookmark else _("Add Bookmark"))
        apply_screen_aware_geometry(self, 640, 760)
        self.minsize(420, 420)
        self.resizable(True, True)
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        self.grab_set()
        
        apply_window_chrome(self)
        
        # Header
        header = tk.Frame(self, bg=theme.bg_dark, height=DesignTokens.HEADER_HEIGHT)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        title = _("Edit bookmark") if bookmark else _("Add bookmark")
        tk.Label(
            header, text=title, bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.title(bold=True)
        ).pack(anchor="w", padx=DesignTokens.PANEL_PAD, pady=(11, 1))
        tk.Label(
            header,
            text=_("Keep the URL, category, tags, and notes clear enough to find later."),
            bg=theme.bg_dark, fg=theme.text_secondary, font=FONTS.small()
        ).pack(anchor="w", padx=DesignTokens.PANEL_PAD, pady=(0, 9))
        
        # Scrollable content keeps the footer reachable on 1280x720 displays.
        body = tk.Frame(self, bg=theme.bg_primary)
        body.pack(fill=tk.BOTH, expand=True, padx=(28, 14), pady=20)
        self.content_canvas = tk.Canvas(
            body, bg=theme.bg_primary, highlightthickness=0, bd=0,
        )
        content_scrollbar = ttk.Scrollbar(
            body, orient=tk.VERTICAL, command=self.content_canvas.yview,
        )
        self.content_canvas.configure(yscrollcommand=content_scrollbar.set)
        self.content_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        content_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))
        content = tk.Frame(self.content_canvas, bg=theme.bg_primary)
        content_window = self.content_canvas.create_window(
            (0, 0), window=content, anchor="nw",
        )
        content.bind(
            "<Configure>",
            lambda _event: self.content_canvas.configure(
                scrollregion=self.content_canvas.bbox("all")
            ),
        )
        self.content_canvas.bind(
            "<Configure>",
            lambda event: self.content_canvas.itemconfigure(
                content_window, width=event.width,
            ),
        )
        self._wheel_binding = bind_scoped_mousewheel(
            self.content_canvas,
            lambda units, _event: self.content_canvas.yview_scroll(units, "units"),
        )
        self.bind("<Prior>", lambda _event: self.content_canvas.yview_scroll(-1, "pages"))
        self.bind("<Next>", lambda _event: self.content_canvas.yview_scroll(1, "pages"))

        tk.Label(
            content, text=_("BOOKMARK DETAILS"), bg=theme.bg_primary,
            fg=theme.text_muted, font=FONTS.tiny(bold=True)
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        
        # URL
        self._create_field(content, _("URL"), 1)
        self.url_var = tk.StringVar(value=bookmark.url if bookmark else "")
        self.url_entry = tk.Entry(
            content, textvariable=self.url_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            highlightthickness=1, highlightbackground=theme.border_muted,
            highlightcolor=theme.border_active, font=FONTS.body()
        )
        self.url_entry.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 4), ipady=8, ipadx=10)
        self.url_feedback = tk.Label(
            content, text=_("Paste a full URL, or type a domain and the app will add https://."),
            bg=theme.bg_primary, fg=theme.text_muted, font=FONTS.tiny(), anchor="w"
        )
        self.url_feedback.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        self.url_var.trace_add("write", lambda *_: self._clear_validation())
        
        # Title
        self._create_field(content, _("Title"), 4)
        self.title_var = tk.StringVar(value=bookmark.title if bookmark else "")
        self.title_entry = tk.Entry(
            content, textvariable=self.title_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            highlightthickness=1, highlightbackground=theme.border_muted,
            highlightcolor=theme.border_active, font=FONTS.body()
        )
        self.title_entry.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 18), ipady=8, ipadx=10)

        tk.Label(
            content, text=_("ORGANIZATION"), bg=theme.bg_primary,
            fg=theme.text_muted, font=FONTS.tiny(bold=True)
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(2, 10))
        
        # Category
        self._create_field(content, _("Category"), 7)
        self.category_var = tk.StringVar(value=bookmark.category if bookmark else "Uncategorized / Needs Review")
        self.category_combo = ttk.Combobox(
            content, textvariable=self.category_var,
            values=self.categories,
            font=FONTS.body()
        )
        self.category_combo.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(0, 15))
        
        # Tags
        self._create_field(content, _("Tags"), 9)
        existing_tags = self.available_tags if self.available_tags else (list(tag_manager.tags.keys()) if tag_manager else [])
        self.tag_editor = TagEditor(
            content, 
            tags=bookmark.tags if bookmark else [],
            available_tags=existing_tags
        )
        self.tag_editor.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(0, 18))

        tk.Label(
            content, text=_("NOTES"), bg=theme.bg_primary,
            fg=theme.text_muted, font=FONTS.tiny(bold=True)
        ).grid(row=11, column=0, columnspan=2, sticky="w", pady=(2, 10))
        
        # Notes
        self.notes_text = tk.Text(
            content, bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            highlightthickness=1, highlightbackground=theme.border_muted,
            highlightcolor=theme.border_active, font=FONTS.body(), height=4,
            wrap=tk.WORD
        )
        self.notes_text.grid(row=12, column=0, columnspan=2, sticky="ew", pady=(0, 18))
        if bookmark and bookmark.notes:
            self.notes_text.insert("1.0", bookmark.notes)
        
        # AI Data Section (read-only display)
        if bookmark and (bookmark.ai_tags or bookmark.ai_confidence > 0 or bookmark.description):
            ai_frame = tk.LabelFrame(
                content, text=_("AI suggestions"), bg=theme.bg_primary,
                fg=theme.text_secondary, font=FONTS.small(bold=True),
                relief=tk.FLAT, bd=1
            )
            ai_frame.grid(row=13, column=0, columnspan=2, sticky="ew", pady=(0, 15))
            
            ai_inner = tk.Frame(ai_frame, bg=theme.bg_primary)
            ai_inner.pack(fill=tk.X, padx=10, pady=10)
            
            if bookmark.ai_confidence > 0:
                conf_row = tk.Frame(ai_inner, bg=theme.bg_primary)
                conf_row.pack(fill=tk.X, pady=2)
                tk.Label(conf_row, text=_("Confidence:"), bg=theme.bg_primary,
                        fg=theme.text_muted, font=FONTS.small(), width=12, anchor="w").pack(side=tk.LEFT)
                conf_color = theme.accent_success if bookmark.ai_confidence >= 0.7 else (
                    theme.accent_warning if bookmark.ai_confidence >= 0.4 else theme.accent_error)
                tk.Label(conf_row, text=format_message('{value_0:.0%}', value_0=bookmark.ai_confidence), bg=theme.bg_primary,
                        fg=conf_color, font=FONTS.tiny(bold=True)).pack(side=tk.LEFT)
            
            if bookmark.ai_tags:
                tags_row = tk.Frame(ai_inner, bg=theme.bg_primary)
                tags_row.pack(fill=tk.X, pady=2)
                tk.Label(tags_row, text=_("AI Tags:"), bg=theme.bg_primary,
                        fg=theme.text_muted, font=FONTS.small(), width=12, anchor="w").pack(side=tk.LEFT)
                tags_text = ", ".join(bookmark.ai_tags)
                tk.Label(tags_row, text=tags_text, bg=theme.bg_primary,
                        fg=theme.accent_primary, font=FONTS.small(), wraplength=350, anchor="w").pack(side=tk.LEFT, fill=tk.X)
                
                # Button to add AI tags to user tags
                def add_ai_tags():
                    current = set(t.lower() for t in self.tag_editor.get_tags())
                    for tag in bookmark.ai_tags:
                        if tag.lower() not in current:
                            self.tag_editor.add_tag(tag)
                            current.add(tag.lower())
                
                add_btn = tk.Label(tags_row, text=_("+ Add"),
                                  bg=theme.accent_primary,
                                  fg=readable_text_on(theme.accent_primary),
                                  font=FONTS.tiny(), padx=5, pady=1, cursor="hand2")
                add_btn.pack(side=tk.RIGHT, padx=5)
                make_keyboard_activatable(add_btn, add_ai_tags)
            
            if bookmark.description:
                desc_row = tk.Frame(ai_inner, bg=theme.bg_primary)
                desc_row.pack(fill=tk.X, pady=2)
                tk.Label(desc_row, text=_("Description:"), bg=theme.bg_primary,
                        fg=theme.text_muted, font=FONTS.small(), width=12, anchor="nw").pack(side=tk.LEFT, anchor="n")
                tk.Label(desc_row, text=bookmark.description[:200], bg=theme.bg_primary,
                        fg=theme.text_secondary, font=FONTS.small(), wraplength=350, 
                        anchor="w", justify=tk.LEFT).pack(side=tk.LEFT, fill=tk.X)
            
            # Adjust row numbers for remaining widgets
            checks_row = 14
        else:
            checks_row = 13
        
        # Checkboxes
        checks_frame = tk.Frame(content, bg=theme.bg_primary)
        checks_frame.grid(row=checks_row, column=0, columnspan=2, sticky="w", pady=(0, 15))
        
        self.pinned_var = tk.BooleanVar(value=bookmark.is_pinned if bookmark else False)
        self.pinned_check = ttk.Checkbutton(
            checks_frame, text=_("Pinned"), variable=self.pinned_var
        )
        self.pinned_check.pack(side=tk.LEFT, padx=(0, 20))
        
        self.archived_var = tk.BooleanVar(value=bookmark.is_archived if bookmark else False)
        self.archived_check = ttk.Checkbutton(
            checks_frame, text=_("Archived"), variable=self.archived_var
        )
        self.archived_check.pack(side=tk.LEFT, padx=(0, 20))

        self.read_later_var = tk.BooleanVar(value=bookmark.read_later if bookmark else False)
        self.read_later_check = ttk.Checkbutton(
            checks_frame, text=_("Read Later"), variable=self.read_later_var
        )
        self.read_later_check.pack(side=tk.LEFT)
        
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        
        # Buttons
        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(fill=tk.X, padx=28, pady=(0, 20))
        
        ModernButton(
            btn_frame, text=_("Cancel"), command=self.destroy
        ).pack(side=tk.RIGHT, padx=(10, 0))

        ModernButton(
            btn_frame, text=_("Save bookmark"), command=self._save,
            style="primary"
        ).pack(side=tk.RIGHT)
        
        if bookmark:
            ModernButton(
                btn_frame, text=_("Open in browser"), command=self._open_url,
            ).pack(side=tk.LEFT)
        
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Control-Return>", lambda e: self._save())
        self.center_window()
        self.url_entry.focus_set()
    
    def _create_field(self, parent, label: str, row: int):
        """Create a field label"""
        theme = get_theme()
        tk.Label(
            parent, text=label, bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.small(bold=True)
        ).grid(row=row, column=0, sticky="w", pady=(0, 5))

    def _clear_validation(self):
        """Reset inline validation once the user edits the URL."""
        if not hasattr(self, "url_feedback"):
            return
        theme = get_theme()
        self.url_feedback.configure(
            text=_("Paste a full URL, or type a domain and the app will add https://."),
            fg=theme.text_muted,
        )
        self.url_entry.configure(highlightbackground=theme.border_muted)

    def _show_url_error(self, message: str):
        """Show URL validation inline instead of interrupting the dialog flow."""
        theme = get_theme()
        self.url_feedback.configure(text=message, fg=theme.accent_error)
        self.url_entry.configure(highlightbackground=theme.accent_error)
    
    def _save(self):
        """Save the bookmark"""
        url = self.url_var.get().strip()
        title = self.title_var.get().strip()
        
        if not url:
            self._show_url_error(_("Enter a bookmark URL before saving."))
            self.url_entry.focus_set()
            return
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Update bookmark object if editing existing
        if self.bookmark:
            self.bookmark.url = url
            self.bookmark.title = title or url
            self.bookmark.category = self.category_var.get()
            self.bookmark.tags = self.tag_editor.get_tags()
            self.bookmark.notes = self.notes_text.get("1.0", tk.END).strip()
            self.bookmark.is_pinned = self.pinned_var.get()
            self.bookmark.is_archived = self.archived_var.get()
            self.bookmark.read_later = self.read_later_var.get()
            self.bookmark.modified_at = datetime.now().isoformat()
            
            # Call on_save callback if provided
            if self.on_save:
                self.on_save(self.bookmark)
        
        self.result = {
            "url": url,
            "title": title or url,
            "category": self.category_var.get(),
            "tags": self.tag_editor.get_tags(),
            "notes": self.notes_text.get("1.0", tk.END).strip(),
            "is_pinned": self.pinned_var.get(),
            "is_archived": self.archived_var.get(),
            "read_later": self.read_later_var.get(),
        }
        self.destroy()
    
    def _open_url(self):
        """Open the URL in browser"""
        url = self.url_var.get().strip()
        if url:
            _open_external_url(url)
    
    def center_window(self):
        """Center the dialog"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')
