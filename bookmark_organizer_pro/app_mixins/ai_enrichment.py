"""AI tag and summary generation workflows."""

from __future__ import annotations

from datetime import datetime
import json
from tkinter import messagebox
from typing import List

try:
    import requests
except ImportError:  # pragma: no cover - optional runtime dependency
    requests = None

from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark


class AiEnrichmentMixin:
    """AI tag suggestion and description-generation workflows."""

    def _ai_suggest_tags(self):
        """AI suggest tags for selected bookmarks"""
        if not self._ensure_ai_ready("AI tag suggestions"):
            return
        
        bookmarks = self._get_selected_bookmarks_for_action(
            "Select Bookmarks",
            "Select one or more bookmarks, then ask AI to suggest tags."
        )
        if not bookmarks:
            return
        
        # Show progress
        self._set_status("Generating AI tags…")
        self.root.update()
        
        try:
            client = self._get_ai_client()
            if not client:
                self._show_ai_client_error("AI tag suggestions")
                return
            
            # Prepare data
            bm_data = [{"url": bm.url, "title": bm.title} for bm in bookmarks]
            categories = self.category_manager.get_sorted_categories()
            
            # Get suggestions (always with tags)
            results = client.categorize_bookmarks(bm_data, categories, 
                                                  allow_new=False, suggest_tags=True)
            
            # Apply tags
            result_map = {r["url"]: r for r in results}
            tagged = 0
            
            for bm in bookmarks:
                result = result_map.get(bm.url)
                if result and result.get("tags"):
                    bm.ai_tags = [t.lower().strip() for t in result["tags"] if t]
                    bm.modified_at = datetime.now().isoformat()
                    tagged += 1
            
            self.bookmark_manager.save_bookmarks()
            self._refresh_bookmark_list()
            
            messagebox.showinfo(
                "Tags Generated",
                f"Generated AI tags for {tagged} bookmark(s).\n\n"
                "AI tags stay separate from your manual tags until you choose to merge them.",
                parent=self.root
            )
            self._set_status(f"Generated tags for {tagged} bookmarks")
            
        except Exception as e:
            log.warning("AI tag suggestions failed", exc_info=True)
            messagebox.showerror(
                "Tag Suggestions Failed",
                f"AI tag suggestions could not be completed.\n\n{str(e)[:240]}",
                parent=self.root
            )
            self._set_status("Tag generation failed")
    
    def _ai_summarize(self):
        """AI generate descriptions for selected bookmarks"""
        if not self._ensure_ai_ready("AI summaries"):
            return
        
        bookmarks = self._get_selected_bookmarks_for_action(
            "Select Bookmarks",
            "Select one or more bookmarks, then ask AI to write descriptions."
        )
        if not bookmarks:
            return
        
        if len(bookmarks) > 10:
            if not messagebox.askyesno(
                "Summarize Selection",
                f"Generate descriptions for {len(bookmarks)} bookmarks?\n\n"
                "Large selections can take longer depending on your provider and rate limit.",
                parent=self.root
            ):
                return
        
        self._set_status("Generating AI summaries…")
        self.root.update()
        
        try:
            client = self._get_ai_client()
            if not client:
                self._show_ai_client_error("AI summaries")
                return
            
            # Build summary prompt
            bm_list = "\n".join([f"- {bm.title} ({bm.url})" for bm in bookmarks[:20]])
            prompt = f"""Analyze these bookmarks and provide a brief description (1-2 sentences) for each explaining what the site/page is about:

{bm_list}

Respond with JSON: {{"summaries": [{{"url": "...", "description": "..."}}]}}"""
            
            # Use the client directly for custom prompt
            provider = self.ai_config.get_provider()
            
            if provider == "openai":
                response = client.client.chat.completions.create(
                    model=client.model,
                    messages=[
                        {"role": "system", "content": "You summarize web pages. Respond only with valid JSON."},
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
                        {"role": "system", "content": "You summarize web pages. Respond only with valid JSON."},
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
                summaries = data.get("summaries", [])
                
                # Apply summaries
                summary_map = {s["url"]: s["description"] for s in summaries}
                updated = 0
                
                for bm in bookmarks:
                    desc = summary_map.get(bm.url)
                    if desc:
                        bm.description = desc
                        bm.modified_at = datetime.now().isoformat()
                        updated += 1
                
                self.bookmark_manager.save_bookmarks()
                self._refresh_bookmark_list()
                
                messagebox.showinfo(
                    "Descriptions Generated",
                    f"Generated descriptions for {updated} bookmark(s).",
                    parent=self.root
                )
                self._set_status(f"Generated {updated} summaries")
            else:
                messagebox.showerror(
                    "AI Response Not Applied",
                    "The AI response was not valid JSON, so no bookmark descriptions were changed.",
                    parent=self.root
                )
                self._set_status("Summary response could not be applied")
                
        except Exception as e:
            log.warning("AI summary generation failed", exc_info=True)
            messagebox.showerror(
                "Summary Generation Failed",
                f"AI summaries could not be completed.\n\n{str(e)[:240]}",
                parent=self.root
            )
            self._set_status("Summary generation failed")
