"""Bookmark editor dialog."""

from __future__ import annotations

from datetime import datetime
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, List

from bookmark_organizer_pro.managers import TagManager
from bookmark_organizer_pro.models import Bookmark

from .foundation import FONTS
from .widget_controls import ModernButton, TagEditor, ThemedWidget
from .widget_runtime import _open_external_url, apply_window_chrome, get_theme

# =============================================================================
# Bookmark Editor Dialog
# =============================================================================
class BookmarkEditorDialog(tk.Toplevel, ThemedWidget):
    """
        Represents a single bookmark with all metadata.
        
        Attributes:
            id: Unique integer identifier
            url: Bookmark URL
            title: Display title
            category: Category name
            tags: List of tag names
            ai_tags: List of AI-suggested tags
            description: Optional description
            favicon_url: URL to favicon image
            created_at: ISO timestamp of creation
            updated_at: ISO timestamp of last update
            visited_at: ISO timestamp of last visit
            visit_count: Number of times visited
            is_valid: Whether URL validation passed
            is_pinned: Whether bookmark is pinned
            ai_category: AI-suggested category
            ai_summary: AI-generated summary
            notes: User notes
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
            matches_search(query): Check if bookmark matches search
        """
    
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
        
        self.title("Edit Bookmark" if bookmark else "Add Bookmark")
        self.geometry("600x700")
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        self.grab_set()
        
        apply_window_chrome(self)
        
        # Header
        header = tk.Frame(self, bg=theme.bg_dark, height=78)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        title = "✏️ Edit bookmark" if bookmark else "➕ Add bookmark"
        tk.Label(
            header, text=title, bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.title(bold=True)
        ).pack(anchor="w", padx=24, pady=(16, 2))
        tk.Label(
            header,
            text="Keep the URL, category, tags, and notes clear enough to find later.",
            bg=theme.bg_dark, fg=theme.text_secondary, font=FONTS.small()
        ).pack(anchor="w", padx=24, pady=(0, 14))
        
        # Content
        content = tk.Frame(self, bg=theme.bg_primary)
        content.pack(fill=tk.BOTH, expand=True, padx=24, pady=18)
        
        # URL
        self._create_field(content, "URL", 0)
        self.url_var = tk.StringVar(value=bookmark.url if bookmark else "")
        self.url_entry = tk.Entry(
            content, textvariable=self.url_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            highlightthickness=1, highlightbackground=theme.border_muted,
            highlightcolor=theme.border_active, font=FONTS.body()
        )
        self.url_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 15), ipady=8, ipadx=10)
        
        # Title
        self._create_field(content, "Title", 2)
        self.title_var = tk.StringVar(value=bookmark.title if bookmark else "")
        self.title_entry = tk.Entry(
            content, textvariable=self.title_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            highlightthickness=1, highlightbackground=theme.border_muted,
            highlightcolor=theme.border_active, font=FONTS.body()
        )
        self.title_entry.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 15), ipady=8, ipadx=10)
        
        # Category
        self._create_field(content, "Category", 4)
        self.category_var = tk.StringVar(value=bookmark.category if bookmark else "Uncategorized / Needs Review")
        self.category_combo = ttk.Combobox(
            content, textvariable=self.category_var,
            values=self.categories,
            font=FONTS.body()
        )
        self.category_combo.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 15))
        
        # Tags
        self._create_field(content, "Tags", 6)
        existing_tags = self.available_tags if self.available_tags else (list(tag_manager.tags.keys()) if tag_manager else [])
        self.tag_editor = TagEditor(
            content, 
            tags=bookmark.tags if bookmark else [],
            available_tags=existing_tags
        )
        self.tag_editor.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(0, 15))
        
        # Notes
        self._create_field(content, "Notes", 8)
        self.notes_text = tk.Text(
            content, bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            highlightthickness=1, highlightbackground=theme.border_muted,
            highlightcolor=theme.border_active, font=FONTS.body(), height=4,
            wrap=tk.WORD
        )
        self.notes_text.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 15))
        if bookmark and bookmark.notes:
            self.notes_text.insert("1.0", bookmark.notes)
        
        # AI Data Section (read-only display)
        if bookmark and (bookmark.ai_tags or bookmark.ai_confidence > 0 or bookmark.description):
            ai_frame = tk.LabelFrame(
                content, text="🤖 AI Data", bg=theme.bg_primary,
                fg=theme.text_secondary, font=FONTS.small(bold=True),
                relief=tk.FLAT, bd=1
            )
            ai_frame.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(0, 15))
            
            ai_inner = tk.Frame(ai_frame, bg=theme.bg_primary)
            ai_inner.pack(fill=tk.X, padx=10, pady=10)
            
            if bookmark.ai_confidence > 0:
                conf_row = tk.Frame(ai_inner, bg=theme.bg_primary)
                conf_row.pack(fill=tk.X, pady=2)
                tk.Label(conf_row, text="Confidence:", bg=theme.bg_primary,
                        fg=theme.text_muted, font=FONTS.small(), width=12, anchor="w").pack(side=tk.LEFT)
                conf_color = theme.accent_success if bookmark.ai_confidence >= 0.7 else (
                    theme.accent_warning if bookmark.ai_confidence >= 0.4 else theme.accent_error)
                tk.Label(conf_row, text=f"{bookmark.ai_confidence:.0%}", bg=theme.bg_primary,
                        fg=conf_color, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
            
            if bookmark.ai_tags:
                tags_row = tk.Frame(ai_inner, bg=theme.bg_primary)
                tags_row.pack(fill=tk.X, pady=2)
                tk.Label(tags_row, text="AI Tags:", bg=theme.bg_primary,
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
                
                add_btn = tk.Label(tags_row, text="+ Add", bg=theme.accent_primary, fg="white",
                                  font=FONTS.tiny(), padx=5, pady=1, cursor="hand2")
                add_btn.pack(side=tk.RIGHT, padx=5)
                add_btn.bind("<Button-1>", lambda e: add_ai_tags())
            
            if bookmark.description:
                desc_row = tk.Frame(ai_inner, bg=theme.bg_primary)
                desc_row.pack(fill=tk.X, pady=2)
                tk.Label(desc_row, text="Description:", bg=theme.bg_primary,
                        fg=theme.text_muted, font=FONTS.small(), width=12, anchor="nw").pack(side=tk.LEFT, anchor="n")
                tk.Label(desc_row, text=bookmark.description[:200], bg=theme.bg_primary,
                        fg=theme.text_secondary, font=FONTS.small(), wraplength=350, 
                        anchor="w", justify=tk.LEFT).pack(side=tk.LEFT, fill=tk.X)
            
            # Adjust row numbers for remaining widgets
            checks_row = 11
        else:
            checks_row = 10
        
        # Checkboxes
        checks_frame = tk.Frame(content, bg=theme.bg_primary)
        checks_frame.grid(row=checks_row, column=0, columnspan=2, sticky="w", pady=(0, 15))
        
        self.pinned_var = tk.BooleanVar(value=bookmark.is_pinned if bookmark else False)
        self.pinned_check = ttk.Checkbutton(
            checks_frame, text="📌 Pinned", variable=self.pinned_var
        )
        self.pinned_check.pack(side=tk.LEFT, padx=(0, 20))
        
        self.archived_var = tk.BooleanVar(value=bookmark.is_archived if bookmark else False)
        self.archived_check = ttk.Checkbutton(
            checks_frame, text="📦 Archived", variable=self.archived_var
        )
        self.archived_check.pack(side=tk.LEFT)
        
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        
        # Buttons
        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(fill=tk.X, padx=24, pady=(0, 18))
        
        ModernButton(
            btn_frame, text="Cancel", command=self.destroy
        ).pack(side=tk.RIGHT, padx=(10, 0))
        
        ModernButton(
            btn_frame, text="Save bookmark", command=self._save,
            style="primary", icon="💾"
        ).pack(side=tk.RIGHT)
        
        if bookmark:
            ModernButton(
                btn_frame, text="Open in browser", command=self._open_url,
                icon="🔗"
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
    
    def _save(self):
        """Save the bookmark"""
        url = self.url_var.get().strip()
        title = self.title_var.get().strip()
        
        if not url:
            messagebox.showerror(
                "URL required",
                "Enter a bookmark URL before saving.",
                parent=self
            )
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
            "is_archived": self.archived_var.get()
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
