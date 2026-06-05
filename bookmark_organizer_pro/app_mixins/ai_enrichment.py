"""AI tag and summary generation workflows with live activity feed."""

from __future__ import annotations

from datetime import datetime
import json
import threading
import time
import tkinter as tk
from tkinter import messagebox
from typing import List

from bookmark_organizer_pro.ai import create_failover_client
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.ai_audit_log import log_tag_suggestion, log_summary
from bookmark_organizer_pro.ui.components import ScrollableFrame
from bookmark_organizer_pro.ui.foundation import FONTS, pluralize
from bookmark_organizer_pro.ui.widgets import ModernButton, apply_window_chrome, get_theme


_SKIP_URL_PATTERNS = (
    "/login", "/signin", "/sign-in", "/auth", "/oauth", "/account",
    "/signup", "/sign-up", "/register", "/password", "/forgot",
    "/logout", "/signout", "/session", "/sso", "/saml",
    "/manage/", "/settings/", "/preferences/",
)

_SKIP_DOMAINS = {
    "login.live.com", "login.microsoftonline.com", "accounts.google.com",
    "login.paylocity.com", "login.one.com", "login.siteground.com",
    "login.teamviewer.com", "auth.tiaa.org", "appleid.apple.com",
    "account.xbox.com", "account.proton.me", "secure.paycor.com",
}


def _should_skip_for_ai(url: str) -> bool:
    """Skip URLs that are login pages, account portals, or auth flows."""
    lower = url.lower()
    try:
        from urllib.parse import urlparse
        host = urlparse(lower).hostname or ""
        if host in _SKIP_DOMAINS:
            return True
    except Exception:
        pass
    return any(p in lower for p in _SKIP_URL_PATTERNS)


class AiEnrichmentMixin:
    """AI tag suggestion and description-generation workflows with live feeds."""

    def _ai_suggest_tags(self):
        if not self._ensure_ai_ready("AI tag suggestions"):
            return

        bookmarks = self._get_selected_bookmarks_for_action(
            "Select Bookmarks",
            "Select one or more bookmarks, then ask AI to suggest tags.",
        )
        if not bookmarks:
            return

        self._run_ai_tags_live(bookmarks)

    def _run_ai_tags_live(self, bookmarks: List[Bookmark]):
        """Tag suggestion with batched API calls and live scrolling feed."""
        theme = get_theme()

        dialog = tk.Toplevel(self.root)
        dialog.title("AI Tag Suggestions — Live")
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("680x520")
        dialog.minsize(580, 400)
        dialog.transient(self.root)
        dialog.grab_set()
        apply_window_chrome(dialog)

        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 680) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 520) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")

        # Header
        header = tk.Frame(dialog, bg=theme.bg_secondary, padx=20, pady=10)
        header.pack(fill=tk.X)

        tk.Label(header, text="AI Tag Suggestions", bg=theme.bg_secondary,
                 fg=theme.text_primary, font=FONTS.subtitle(bold=True)).pack(side=tk.LEFT)

        stats_label = tk.Label(header, text=f"0 / {len(bookmarks)}", bg=theme.bg_secondary,
                               fg=theme.text_secondary, font=FONTS.body())
        stats_label.pack(side=tk.RIGHT)

        # Progress bar
        bar_bg = tk.Frame(dialog, bg=theme.bg_tertiary, height=4)
        bar_bg.pack(fill=tk.X)
        bar_fill = tk.Frame(bar_bg, bg=theme.accent_primary, height=4)
        bar_fill.place(x=0, y=0, relheight=1.0, relwidth=0)

        # Live feed
        feed_frame = ScrollableFrame(dialog, bg=theme.bg_primary)
        feed_frame.pack(fill=tk.BOTH, expand=True)
        feed = feed_frame.inner

        # Footer
        footer = tk.Frame(dialog, bg=theme.bg_secondary, padx=16, pady=10)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        status_label = tk.Label(footer, text="Starting…", bg=theme.bg_secondary,
                                fg=theme.text_muted, font=FONTS.small())
        status_label.pack(side=tk.LEFT)

        cancelled = [False]

        def cancel():
            cancelled[0] = True
            cancel_btn.set_state("disabled")
            cancel_btn.set_text("Stopping…")

        cancel_btn = ModernButton(footer, text="Stop", command=cancel, padx=14, pady=5)
        cancel_btn.pack(side=tk.RIGHT)

        done_btn = ModernButton(footer, text="Done", style="success", padx=14, pady=5,
                                command=lambda: [dialog.grab_release(), dialog.destroy()])

        def _add_entry(bm, tags_added, all_tags):
            if not dialog.winfo_exists():
                return
            row = tk.Frame(feed, bg=theme.bg_primary, padx=12, pady=4)
            row.pack(fill=tk.X, pady=1)

            dot_color = theme.accent_success if tags_added else theme.text_muted
            dot_char = "✓" if tags_added else "–"
            tk.Label(row, text=dot_char, bg=theme.bg_primary, fg=dot_color,
                     font=FONTS.body(bold=True), width=2).pack(side=tk.LEFT, padx=(0, 6))

            info = tk.Frame(row, bg=theme.bg_primary)
            info.pack(side=tk.LEFT, fill=tk.X, expand=True)

            tk.Label(info, text=(bm.title or bm.url)[:50], bg=theme.bg_primary,
                     fg=theme.text_primary, font=FONTS.body(), anchor="w").pack(anchor="w")

            if all_tags:
                tk.Label(info, text=", ".join(all_tags[:6]), bg=theme.bg_primary,
                         fg=theme.accent_primary, font=FONTS.small(), anchor="w").pack(anchor="w")

            feed_frame.canvas.update_idletasks()
            feed_frame.canvas.yview_moveto(1.0)

        def _clean_tags(tags, domain):
            """Post-process AI tags: remove domain names and generic words."""
            domain_parts = set()
            if domain:
                domain_parts = {p.lower() for p in domain.replace(".", " ").replace("-", " ").split() if len(p) > 2}
                domain_parts.add(domain.split(".")[0].lower())
            BAD_TAGS = {"blog", "website", "page", "online", "web", "app", "site",
                        "home", "index", "default", "main", "login", "account",
                        "www", "com", "org", "net", "http", "https"}
            cleaned = []
            for tag in tags:
                t = tag.lower().strip()
                if not t or len(t) < 2:
                    continue
                if t in BAD_TAGS or t in domain_parts:
                    continue
                cleaned.append(t)
            return cleaned

        def _worker():
            client = create_failover_client(self.ai_config)
            categories = self.category_manager.get_sorted_categories()
            batch_size = self.ai_config.get_batch_size()
            rate_delay = max(0.1, 60.0 / max(1, self.ai_config.get_rate_limit()))
            provider = self.ai_config.get_provider()
            model = self.ai_config.get_model()

            processed = 0
            tagged = 0
            skipped_urls = 0

            for start in range(0, len(bookmarks), batch_size):
                if cancelled[0]:
                    break

                end = min(start + batch_size, len(bookmarks))
                batch = bookmarks[start:end]

                # Filter out login/account pages
                real_batch = []
                skip_batch = []
                for bm in batch:
                    if _should_skip_for_ai(bm.url):
                        skip_batch.append(bm)
                    else:
                        real_batch.append(bm)

                # Show skipped entries
                for bm in skip_batch:
                    skipped_urls += 1
                    processed += 1
                    self.root.after(0, lambda b=bm: _add_entry(b, False, ["(skipped — login/auth page)"]))
                    self.root.after(0, lambda p=processed: [
                        stats_label.configure(text=f"{p} / {len(bookmarks)}"),
                        bar_fill.place(relwidth=p / len(bookmarks)),
                    ])

                if not real_batch:
                    continue

                bm_data = [{"url": bm.url, "title": bm.title} for bm in real_batch]

                self.root.after(0, lambda s=start, e=end: status_label.configure(
                    text=f"Processing {s+1}–{e} of {len(bookmarks)}…"))

                try:
                    results = client.categorize_bookmarks(
                        bm_data, categories, allow_new=False, suggest_tags=True)
                    result_map = {r.get("url", ""): r for r in results}
                except Exception as exc:
                    log.warning(f"AI tag batch failed: {exc}")
                    for bm in real_batch:
                        processed += 1
                        self.root.after(0, lambda b=bm: _add_entry(b, False, []))
                    continue

                for bm in real_batch:
                    if cancelled[0]:
                        break

                    result = result_map.get(bm.url, {})
                    ai_tags_raw = result.get("tags", [])
                    ai_tags_clean = _clean_tags(ai_tags_raw, bm.domain)

                    if ai_tags_clean:
                        old_tags = list(bm.tags)
                        # Add to BOTH ai_tags AND regular tags
                        bm.ai_tags = ai_tags_clean
                        existing = {t.lower() for t in bm.tags}
                        new_tags_added = []
                        for tag in ai_tags_clean:
                            if tag.lower() not in existing:
                                bm.tags.append(tag)
                                existing.add(tag.lower())
                                new_tags_added.append(tag)

                        bm.modified_at = datetime.now().isoformat()
                        tagged += 1

                        log_tag_suggestion(
                            provider=client.last_provider if hasattr(client, 'last_provider') else provider,
                            model=client.last_model if hasattr(client, 'last_model') else model,
                            bookmark_id=bm.id, url=bm.url,
                            old_tags=old_tags, new_tags=list(bm.tags),
                            ai_tags=ai_tags_clean, applied=True,
                        )
                        self.root.after(0, lambda b=bm, t=new_tags_added: _add_entry(b, True, t))
                    else:
                        self.root.after(0, lambda b=bm: _add_entry(b, False, []))

                    processed += 1
                    self.root.after(0, lambda p=processed: [
                        stats_label.configure(text=f"{p} / {len(bookmarks)}"),
                        bar_fill.place(relwidth=p / len(bookmarks)),
                    ])

                # Save periodically
                self.bookmark_manager.save_bookmarks()

                if not cancelled[0] and end < len(bookmarks):
                    time.sleep(rate_delay)

            self.bookmark_manager.save_bookmarks()

            def _finish():
                if not dialog.winfo_exists():
                    return
                bar_fill.configure(bg=theme.accent_success)
                bar_fill.place(relwidth=1.0)
                cancel_btn.pack_forget()
                done_btn.pack(side=tk.RIGHT)
                summary = f"Done — {tagged} tagged, {processed - tagged - skipped_urls} unchanged"
                if skipped_urls:
                    summary += f", {skipped_urls} login/auth pages skipped"
                status_label.configure(text=summary, fg=theme.text_primary)
                self._refresh_all()

            self.root.after(0, _finish)

        threading.Thread(target=_worker, daemon=True).start()

    def _ai_summarize(self):
        if not self._ensure_ai_ready("AI summaries"):
            return

        bookmarks = self._get_selected_bookmarks_for_action(
            "Select Bookmarks",
            "Select one or more bookmarks, then ask AI to write descriptions.",
        )
        if not bookmarks:
            return

        if len(bookmarks) > 10:
            if not messagebox.askyesno(
                "Summarize Selection",
                f"Generate descriptions for {len(bookmarks)} bookmarks?\n\n"
                "Large selections can take longer depending on your provider and rate limit.",
                parent=self.root,
            ):
                return

        self._run_ai_summaries_live(bookmarks)

    def _run_ai_summaries_live(self, bookmarks: List[Bookmark]):
        """Summary generation with batched calls and live feed."""
        theme = get_theme()

        dialog = tk.Toplevel(self.root)
        dialog.title("AI Summaries — Live")
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("680x520")
        dialog.minsize(580, 400)
        dialog.transient(self.root)
        dialog.grab_set()
        apply_window_chrome(dialog)

        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 680) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 520) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")

        header = tk.Frame(dialog, bg=theme.bg_secondary, padx=20, pady=10)
        header.pack(fill=tk.X)
        tk.Label(header, text="AI Summaries", bg=theme.bg_secondary,
                 fg=theme.text_primary, font=FONTS.subtitle(bold=True)).pack(side=tk.LEFT)
        stats_label = tk.Label(header, text=f"0 / {len(bookmarks)}", bg=theme.bg_secondary,
                               fg=theme.text_secondary, font=FONTS.body())
        stats_label.pack(side=tk.RIGHT)

        bar_bg = tk.Frame(dialog, bg=theme.bg_tertiary, height=4)
        bar_bg.pack(fill=tk.X)
        bar_fill = tk.Frame(bar_bg, bg=theme.accent_primary, height=4)
        bar_fill.place(x=0, y=0, relheight=1.0, relwidth=0)

        feed_frame = ScrollableFrame(dialog, bg=theme.bg_primary)
        feed_frame.pack(fill=tk.BOTH, expand=True)
        feed = feed_frame.inner

        footer = tk.Frame(dialog, bg=theme.bg_secondary, padx=16, pady=10)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        status_label = tk.Label(footer, text="Starting…", bg=theme.bg_secondary,
                                fg=theme.text_muted, font=FONTS.small())
        status_label.pack(side=tk.LEFT)

        cancelled = [False]
        cancel_btn = ModernButton(footer, text="Stop", command=lambda: [
            cancelled.__setitem__(0, True), cancel_btn.set_state("disabled")], padx=14, pady=5)
        cancel_btn.pack(side=tk.RIGHT)
        done_btn = ModernButton(footer, text="Done", style="success", padx=14, pady=5,
                                command=lambda: [dialog.grab_release(), dialog.destroy()])

        def _add_entry(bm, desc, success):
            if not dialog.winfo_exists():
                return
            row = tk.Frame(feed, bg=theme.bg_primary, padx=12, pady=4)
            row.pack(fill=tk.X, pady=1)

            dot = "✓" if success else "–"
            tk.Label(row, text=dot, bg=theme.bg_primary,
                     fg=theme.accent_success if success else theme.text_muted,
                     font=FONTS.body(bold=True), width=2).pack(side=tk.LEFT, padx=(0, 6))

            info = tk.Frame(row, bg=theme.bg_primary)
            info.pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Label(info, text=(bm.title or bm.url)[:50], bg=theme.bg_primary,
                     fg=theme.text_primary, font=FONTS.body(), anchor="w").pack(anchor="w")
            if desc:
                tk.Label(info, text=desc[:80], bg=theme.bg_primary,
                         fg=theme.text_muted, font=FONTS.small(), anchor="w").pack(anchor="w")

            feed_frame.canvas.update_idletasks()
            feed_frame.canvas.yview_moveto(1.0)

        def _worker():
            client = self._get_ai_client()
            if not client:
                self.root.after(0, lambda: messagebox.showerror("Error", "AI client unavailable", parent=dialog))
                return

            provider = self.ai_config.get_provider()
            model = self.ai_config.get_model()
            batch_size = min(self.ai_config.get_batch_size(), 15)
            rate_delay = max(0.1, 60.0 / max(1, self.ai_config.get_rate_limit()))

            processed = 0
            updated = 0

            for start in range(0, len(bookmarks), batch_size):
                if cancelled[0]:
                    break
                end = min(start + batch_size, len(bookmarks))
                batch = bookmarks[start:end]

                self.root.after(0, lambda s=start, e=end: status_label.configure(
                    text=f"Processing {s+1}–{e} of {len(bookmarks)}…"))

                bm_list = "\n".join([f"- {bm.title} ({bm.url})" for bm in batch])
                prompt = (
                    f"Analyze these bookmarks and provide a brief description (1-2 sentences) "
                    f"for each explaining what the site/page is about:\n\n{bm_list}\n\n"
                    f'Respond with JSON: {{"summaries": [{{"url": "...", "description": "..."}}]}}'
                )

                try:
                    text = client.complete(
                        prompt, system="You summarize web pages. Respond only with valid JSON.",
                        max_tokens=2048, temperature=0.3,
                    )
                    json_text = self._extract_json_object_text(text)
                    if json_text:
                        data = json.loads(json_text)
                        summary_map = {s["url"]: s["description"] for s in data.get("summaries", [])}

                        for bm in batch:
                            desc = summary_map.get(bm.url)
                            if desc:
                                bm.description = desc
                                bm.modified_at = datetime.now().isoformat()
                                updated += 1
                                log_summary(provider=provider, model=model,
                                            bookmark_id=bm.id, url=bm.url, summary=desc)
                                self.root.after(0, lambda b=bm, d=desc: _add_entry(b, d, True))
                            else:
                                self.root.after(0, lambda b=bm: _add_entry(b, "", False))
                            processed += 1
                    else:
                        for bm in batch:
                            self.root.after(0, lambda b=bm: _add_entry(b, "", False))
                            processed += 1
                except Exception as exc:
                    log.warning(f"AI summary batch failed: {exc}")
                    for bm in batch:
                        self.root.after(0, lambda b=bm: _add_entry(b, "", False))
                        processed += 1

                self.root.after(0, lambda p=processed: [
                    stats_label.configure(text=f"{p} / {len(bookmarks)}"),
                    bar_fill.place(relwidth=p / len(bookmarks)),
                ])

                self.bookmark_manager.save_bookmarks()
                if not cancelled[0] and end < len(bookmarks):
                    time.sleep(rate_delay)

            self.bookmark_manager.save_bookmarks()

            def _finish():
                if not dialog.winfo_exists():
                    return
                bar_fill.configure(bg=theme.accent_success)
                bar_fill.place(relwidth=1.0)
                cancel_btn.pack_forget()
                done_btn.pack(side=tk.RIGHT)
                status_label.configure(text=f"Done — {updated} summaries generated", fg=theme.text_primary)
                self._refresh_all()

            self.root.after(0, _finish)

        threading.Thread(target=_worker, daemon=True).start()
