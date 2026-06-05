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
from bookmark_organizer_pro.services.ai_audit_log import log_tag_suggestion, log_summary


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
        
        self._set_status("Generating AI tags…")

        import threading

        client = self._get_ai_client()
        if not client:
            self._show_ai_client_error("AI tag suggestions")
            return

        bm_data = [{"url": bm.url, "title": bm.title} for bm in bookmarks]
        categories = self.category_manager.get_sorted_categories()

        def _worker():
            try:
                results = client.categorize_bookmarks(bm_data, categories, allow_new=False, suggest_tags=True)
                self.root.after(0, lambda: _on_done(results, None))
            except Exception as exc:
                self.root.after(0, lambda: _on_done(None, exc))

        def _on_done(results, error):
            if error:
                log.warning("AI tag suggestions failed", exc_info=True)
                messagebox.showerror("Tag Suggestions Failed", f"AI tag suggestions could not be completed.\n\n{str(error)[:240]}", parent=self.root)
                self._set_status("Tag generation failed")
                return
            result_map = {r["url"]: r for r in results}
            tagged = 0
            provider = self.ai_config.get_provider()
            model = self.ai_config.get_model()
            for bm in bookmarks:
                result = result_map.get(bm.url)
                if result and result.get("tags"):
                    old_tags = list(bm.ai_tags)
                    bm.ai_tags = [t.lower().strip() for t in result["tags"] if t]
                    bm.modified_at = datetime.now().isoformat()
                    tagged += 1
                    log_tag_suggestion(
                        provider=provider, model=model,
                        bookmark_id=bm.id, url=bm.url,
                        old_tags=old_tags, new_tags=list(bm.ai_tags),
                        ai_tags=result["tags"], applied=True,
                    )
            self.bookmark_manager.save_bookmarks()
            self._refresh_bookmark_list()
            messagebox.showinfo("Tags Generated", f"Generated AI tags for {tagged} bookmark(s).\n\nAI tags stay separate from your manual tags until you choose to merge them.", parent=self.root)
            self._set_status(f"Generated tags for {tagged} bookmarks")

        threading.Thread(target=_worker, daemon=True).start()
    
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

        import threading

        client = self._get_ai_client()
        if not client:
            self._show_ai_client_error("AI summaries")
            return

        bm_list = "\n".join([f"- {bm.title} ({bm.url})" for bm in bookmarks[:20]])
        prompt = f"""Analyze these bookmarks and provide a brief description (1-2 sentences) for each explaining what the site/page is about:

{bm_list}

Respond with JSON: {{"summaries": [{{"url": "...", "description": "..."}}]}}"""

        def _worker():
            try:
                text = client.complete(prompt, system="You summarize web pages. Respond only with valid JSON.", max_tokens=2048, temperature=0.3)
                self.root.after(0, lambda: _on_done(text, None))
            except Exception as exc:
                self.root.after(0, lambda: _on_done(None, exc))

        def _on_done(text, error):
            if error:
                log.warning("AI summary generation failed", exc_info=True)
                messagebox.showerror("Summary Generation Failed", f"AI summaries could not be completed.\n\n{str(error)[:240]}", parent=self.root)
                self._set_status("Summary generation failed")
                return
            json_text = self._extract_json_object_text(text)
            if json_text:
                data = json.loads(json_text)
                summaries = data.get("summaries", [])
                summary_map = {s["url"]: s["description"] for s in summaries}
                updated = 0
                provider = self.ai_config.get_provider()
                model = self.ai_config.get_model()
                for bm in bookmarks:
                    desc = summary_map.get(bm.url)
                    if desc:
                        bm.description = desc
                        bm.modified_at = datetime.now().isoformat()
                        updated += 1
                        log_summary(
                            provider=provider, model=model,
                            bookmark_id=bm.id, url=bm.url,
                            summary=desc, applied=True,
                        )
                self.bookmark_manager.save_bookmarks()
                self._refresh_bookmark_list()
                messagebox.showinfo("Descriptions Generated", f"Generated descriptions for {updated} bookmark(s).", parent=self.root)
                self._set_status(f"Generated {updated} summaries")
            else:
                messagebox.showerror("AI Response Not Applied", "The AI response was not valid JSON, so no bookmark descriptions were changed.", parent=self.root)
                self._set_status("Summary response could not be applied")

        threading.Thread(target=_worker, daemon=True).start()
