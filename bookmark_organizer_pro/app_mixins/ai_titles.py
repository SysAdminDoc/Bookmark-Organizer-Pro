"""AI title improvement workflow and preview dialog."""

from __future__ import annotations

from datetime import datetime
import json
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, List

try:
    import requests
except ImportError:  # pragma: no cover - optional runtime dependency
    requests = None

from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.ui.foundation import FONTS
from bookmark_organizer_pro.ui.widgets import ModernButton, apply_window_chrome, get_theme


class AiTitleImprovementMixin:
    """AI title suggestion and preview workflow."""

    def _ai_improve_titles(self):
        """AI improve bookmark titles to be more descriptive"""
        if not self._ensure_ai_ready("AI title improvements"):
            return
        
        bookmarks = self._get_selected_bookmarks_for_action(
            "Select Bookmarks",
            "Select one or more bookmarks, then ask AI to suggest cleaner titles."
        )
        if not bookmarks:
            return
        
        if len(bookmarks) > 20:
            if not messagebox.askyesno(
                "Improve Titles",
                f"Suggest title improvements for {len(bookmarks)} bookmarks?\n\n"
                "You will preview the suggestions before anything is changed.",
                parent=self.root
            ):
                return
        
        self._set_status("Improving bookmark titles with AI…")
        self.root.update()
        
        try:
            client = self._get_ai_client()
            if not client:
                self._show_ai_client_error("AI title improvements")
                return
            
            # Build prompt for title improvement
            bm_list = []
            for bm in bookmarks[:30]:  # Limit to 30
                bm_list.append({
                    "url": bm.url,
                    "current_title": bm.title,
                    "domain": bm.domain
                })
            
            prompt = f"""Analyze these bookmarks and suggest better, more descriptive titles. 
The new titles should be:
- Clear and descriptive (explain what the page is about)
- Concise (under 60 characters ideally)
- Remove unnecessary prefixes like "Home |" or "Welcome to"
- Remove trailing site names if redundant with domain
- Fix capitalization issues
- Keep technical terms accurate

Bookmarks:
{json.dumps(bm_list, indent=2)}

Respond with ONLY valid JSON in this exact format:
{{"titles": [{{"url": "https://example.com", "new_title": "Improved Title Here"}}]}}"""
            
            # Use the client directly for custom prompt
            provider = self.ai_config.get_provider()
            
            if provider == "openai":
                response = client.client.chat.completions.create(
                    model=client.model,
                    messages=[
                        {"role": "system", "content": "You improve bookmark titles to be more descriptive and useful. Respond only with valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                text = (response.choices[0].message.content if response.choices else '')
            elif provider == "anthropic":
                response = client.client.messages.create(
                    model=client.model,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}]
                )
                text = (response.content[0].text if response.content else '')
            elif provider == "google":
                response = client.client.generate_content(prompt)
                text = response.text
            elif provider == "groq":
                response = client.client.chat.completions.create(
                    model=client.model,
                    messages=[
                        {"role": "system", "content": "You improve bookmark titles. Respond only with valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                text = (response.choices[0].message.content if response.choices else '')
            else:  # ollama
                response = requests.post(
                    f"{client.base_url}/api/generate",
                    json={"model": client.model, "prompt": prompt, "stream": False},
                    timeout=120
                )
                text = response.json()["response"]
            
            # Parse response
            json_text = self._extract_json_object_text(text)
            if json_text:
                data = json.loads(json_text)
                titles = data.get("titles", [])
                
                # Show preview dialog before applying
                self._show_title_preview(bookmarks, titles)
            else:
                messagebox.showerror(
                    "AI Response Not Applied",
                    "The AI response was not valid JSON, so no bookmark titles were changed.",
                    parent=self.root
                )
                self._set_status("Title suggestions could not be applied")
                
        except Exception as e:
            log.warning("AI title improvement failed", exc_info=True)
            messagebox.showerror(
                "Title Improvement Failed",
                f"AI title suggestions could not be completed.\n\n{str(e)[:240]}",
                parent=self.root
            )
            self._set_status("Title improvement failed")
    
    def _show_title_preview(self, bookmarks: List[Bookmark], titles: List[Dict]):
        """Show preview of title changes before applying"""
        theme = get_theme()
        
        # Create title mapping
        title_map = {t["url"]: t["new_title"] for t in titles}
        
        # Find bookmarks with actual changes
        changes = []
        for bm in bookmarks:
            new_title = title_map.get(bm.url)
            if new_title and new_title != bm.title:
                changes.append((bm, new_title))
        
        if not changes:
            messagebox.showinfo(
                "No Title Changes",
                "AI did not suggest any title improvements for the selected bookmarks.",
                parent=self.root
            )
            return
        
        # Create preview dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Preview Title Changes")
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("700x500")
        dialog.transient(self.root)
        dialog.grab_set()
        apply_window_chrome(dialog)
        
        # Center
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 700) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 500) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Header
        header = tk.Frame(dialog, bg=theme.bg_secondary, padx=20, pady=15)
        header.pack(fill=tk.X)
        
        tk.Label(
            header, text="Preview title changes", bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.title(bold=True)
        ).pack(anchor="w")
        tk.Label(
            header,
            text=f"Review {len(changes)} suggested title update(s) before applying them.",
            bg=theme.bg_secondary, fg=theme.text_secondary,
            font=FONTS.small(), wraplength=640, justify=tk.LEFT
        ).pack(anchor="w", pady=(4, 0))
        
        # Scrollable list of changes
        canvas = tk.Canvas(dialog, bg=theme.bg_primary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=theme.bg_primary)
        
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=20, pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Track which changes to apply
        check_vars = []
        
        for bm, new_title in changes:
            frame = tk.Frame(scroll_frame, bg=theme.bg_tertiary, padx=10, pady=8)
            frame.pack(fill=tk.X, pady=3, padx=5)
            
            var = tk.BooleanVar(value=True)
            check_vars.append((bm, new_title, var))
            
            cb = ttk.Checkbutton(frame, variable=var)
            cb.pack(side=tk.LEFT, padx=(0, 10))
            
            text_frame = tk.Frame(frame, bg=theme.bg_tertiary)
            text_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            # Domain
            tk.Label(text_frame, text=bm.domain, bg=theme.bg_tertiary,
                    fg=theme.text_muted, font=FONTS.tiny()).pack(anchor="w")
            
            # Old title
            tk.Label(
                text_frame, text=f"Current: {bm.title[:90]}", bg=theme.bg_tertiary,
                fg=theme.text_secondary, font=FONTS.small(),
                wraplength=560, justify=tk.LEFT
            ).pack(anchor="w")
            
            # New title
            tk.Label(
                text_frame, text=f"Suggested: {new_title[:90]}", bg=theme.bg_tertiary,
                fg=theme.accent_success, font=FONTS.small(bold=True),
                wraplength=560, justify=tk.LEFT
            ).pack(anchor="w", pady=(2, 0))
        
        # Buttons
        btn_frame = tk.Frame(dialog, bg=theme.bg_secondary, pady=15)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        def apply_changes():
            applied = 0
            for bm, new_title, var in check_vars:
                if var.get():
                    bm.title = new_title
                    bm.modified_at = datetime.now().isoformat()
                    applied += 1
            
            self.bookmark_manager.save_bookmarks()
            self._refresh_bookmark_list()
            dialog.destroy()
            
            messagebox.showinfo(
                "Titles Updated",
                f"Updated {applied} bookmark title(s).",
                parent=self.root
            )
            self._set_status(f"Updated {applied} titles")
        
        def select_all():
            for _, _, var in check_vars:
                var.set(True)
        
        def select_none():
            for _, _, var in check_vars:
                var.set(False)
        
        ModernButton(btn_frame, text="Select all", command=select_all, padx=12, pady=6).pack(side=tk.LEFT, padx=(20, 8))
        ModernButton(btn_frame, text="Select none", command=select_none, padx=12, pady=6).pack(side=tk.LEFT)
        ModernButton(btn_frame, text="Apply selected", command=apply_changes, style="success", padx=20, pady=8).pack(side=tk.RIGHT, padx=20)
        ModernButton(btn_frame, text="Cancel", command=dialog.destroy, padx=16, pady=8).pack(side=tk.RIGHT)
        dialog.bind("<Escape>", lambda e: dialog.destroy())
