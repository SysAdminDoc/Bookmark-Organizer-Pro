"""AI categorization workflow with live activity feed and failover support."""

from __future__ import annotations

from datetime import datetime
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Dict, List

from bookmark_organizer_pro.ai import create_failover_client
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.ai_audit_log import log_categorize, log_title_improvement
from bookmark_organizer_pro.ui.components import ScrollableFrame
from bookmark_organizer_pro.ui.foundation import FONTS, DesignTokens, pluralize
from bookmark_organizer_pro.ui.widgets import ModernButton, apply_window_chrome, get_theme


class AiCategorizationMixin:
    """AI categorization with live result feed and automatic failover."""

    def _ai_categorize(self):
        if not self._ensure_ai_ready("AI categorization"):
            return

        bookmarks = self._get_selected_bookmarks_for_action(
            "Select Bookmarks",
            "Select one or more bookmarks, then run AI categorization.",
        )
        if not bookmarks:
            return

        failover_note = ""
        if self.ai_config.get_failover_enabled():
            fp = self.ai_config.get_failover_provider()
            fm = self.ai_config.get_failover_model()
            failover_note = f"\nFailover: {fp} / {fm} (below {int(self.ai_config.get_failover_confidence_threshold() * 100)}% confidence)"

        if not messagebox.askyesno(
            "Categorize with AI",
            f"Categorize {len(bookmarks)} bookmark(s) with AI?\n\n"
            f"Provider: {self._ai_provider_name()}\n"
            f"Model: {self.ai_config.get_model()}\n"
            f"Confidence threshold: {int(self.ai_config.get_min_confidence() * 100)}%"
            f"{failover_note}",
            parent=self.root,
        ):
            return

        self._run_ai_categorization_live(bookmarks)

    def _run_ai_categorization_live(self, bookmarks: List[Bookmark]):
        """Run AI categorization with a live scrolling activity feed."""
        theme = get_theme()

        dialog = tk.Toplevel(self.root)
        dialog.title("AI Categorization — Live")
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("700x580")
        dialog.minsize(600, 450)
        dialog.transient(self.root)
        dialog.grab_set()
        apply_window_chrome(dialog)

        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 700) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 580) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")

        # ── Header ──
        header = tk.Frame(dialog, bg=theme.bg_secondary, padx=20, pady=12)
        header.pack(fill=tk.X)

        tk.Label(
            header, text="AI Categorization", bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.subtitle(bold=True),
        ).pack(side=tk.LEFT)

        stats_label = tk.Label(
            header, text=f"0 / {len(bookmarks)}", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.body(),
        )
        stats_label.pack(side=tk.RIGHT)

        # ── Progress bar ──
        bar_bg = tk.Frame(dialog, bg=theme.bg_tertiary, height=4)
        bar_bg.pack(fill=tk.X)
        bar_fill = tk.Frame(bar_bg, bg=theme.accent_primary, height=4)
        bar_fill.place(x=0, y=0, relheight=1.0, relwidth=0)

        # ── Live activity feed (scrollable) ──
        feed_frame = ScrollableFrame(dialog, bg=theme.bg_primary)
        feed_frame.pack(fill=tk.BOTH, expand=True)
        feed = feed_frame.inner

        # ── Footer ──
        footer = tk.Frame(dialog, bg=theme.bg_secondary, padx=16, pady=10)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        status_label = tk.Label(
            footer, text="Starting…", bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.small(),
        )
        status_label.pack(side=tk.LEFT)

        cancelled = [False]

        def cancel():
            cancelled[0] = True
            cancel_btn.set_state("disabled")
            cancel_btn.set_text("Stopping…")

        cancel_btn = ModernButton(footer, text="Stop", command=cancel, padx=14, pady=5)
        cancel_btn.pack(side=tk.RIGHT)

        done_btn = ModernButton(footer, text="Done", style="success", padx=14, pady=5,
                                command=lambda: _close())
        # hidden until complete

        def _close():
            dialog.grab_release()
            dialog.destroy()

        # ── Feed entry builder ──
        def _add_feed_entry(bm: Bookmark, result: Dict, applied: bool,
                            reason: str, provider_used: str, is_failover: bool):
            if not dialog.winfo_exists():
                return

            row = tk.Frame(feed, bg=theme.bg_primary, padx=12, pady=6)
            row.pack(fill=tk.X, pady=1)

            # Left: status dot
            if applied:
                dot_color = theme.accent_success
                dot_char = "✓"
            elif reason.startswith("confidence"):
                dot_color = theme.accent_warning
                dot_char = "~"
            else:
                dot_color = theme.text_muted
                dot_char = "–"

            tk.Label(
                row, text=dot_char, bg=theme.bg_primary,
                fg=dot_color, font=FONTS.body(bold=True), width=2,
            ).pack(side=tk.LEFT, padx=(0, 6))

            # Middle: bookmark info
            info = tk.Frame(row, bg=theme.bg_primary)
            info.pack(side=tk.LEFT, fill=tk.X, expand=True)

            title_text = (bm.title or bm.url)[:55]
            tk.Label(
                info, text=title_text, bg=theme.bg_primary,
                fg=theme.text_primary, font=FONTS.body(), anchor="w",
            ).pack(anchor="w")

            # Change details
            old_cat = result.get("_old_category", bm.category)
            new_cat = result.get("category", old_cat)
            conf = result.get("confidence", 0)
            tags = result.get("tags", [])

            detail_parts = []
            if applied and new_cat != old_cat:
                detail_parts.append(f"{old_cat} → {new_cat}")
            elif not applied:
                detail_parts.append(f"kept: {old_cat}")

            detail_parts.append(f"{conf:.0%}")

            if is_failover:
                detail_parts.append(f"via {provider_used}")

            if tags:
                detail_parts.append(f"tags: {', '.join(tags[:4])}")

            tk.Label(
                info, text="  ·  ".join(detail_parts),
                bg=theme.bg_primary, fg=theme.text_muted,
                font=FONTS.small(), anchor="w",
            ).pack(anchor="w")

            # Auto-scroll to bottom
            feed_frame.canvas.update_idletasks()
            feed_frame.canvas.yview_moveto(1.0)

        # ── Background worker ──
        def _worker():
            client = create_failover_client(self.ai_config)
            categories = self.category_manager.get_sorted_categories()
            allow_new = self.ai_config.get_auto_create_categories()
            suggest_tags = self.ai_config.get_suggest_tags()
            min_confidence = self.ai_config.get_min_confidence()
            batch_size = self.ai_config.get_batch_size()
            rate_delay = max(0.1, 60.0 / max(1, self.ai_config.get_rate_limit()))

            processed = 0
            applied_count = 0
            failover_count = 0
            new_categories = set()
            titles_changed = 0

            for start in range(0, len(bookmarks), batch_size):
                if cancelled[0]:
                    break

                end = min(start + batch_size, len(bookmarks))
                batch = bookmarks[start:end]
                bm_data = [{"url": bm.url, "title": bm.title} for bm in batch]

                self.root.after(0, lambda s=start, e=end: status_label.configure(
                    text=f"Processing {s+1}–{e} of {len(bookmarks)}… ({client.last_provider}/{client.last_model})",
                ))

                try:
                    results = client.categorize_bookmarks(bm_data, categories, allow_new, suggest_tags)
                except Exception as exc:
                    log.warning(f"AI batch failed: {exc}")
                    for bm in batch:
                        self.root.after(0, lambda b=bm: _add_feed_entry(
                            b, {}, False, f"error: {str(exc)[:40]}", client.last_provider, False,
                        ))
                    processed += len(batch)
                    continue

                result_map = {r.get("url", ""): r for r in results}

                for bm in batch:
                    if cancelled[0]:
                        break

                    result = result_map.get(bm.url, {})
                    confidence = result.get("confidence", 0)
                    is_failover = result.get("_failover", False)
                    provider_used = result.get("_failover_provider", client.last_provider)

                    result["_old_category"] = bm.category
                    old_category = bm.category
                    old_title = bm.title

                    applied = False
                    reason = ""

                    if confidence < min_confidence:
                        reason = f"confidence {confidence:.0%} < {min_confidence:.0%}"
                        log_categorize(
                            provider=provider_used,
                            model=result.get("_failover_model", client.last_model),
                            bookmark_id=bm.id, url=bm.url,
                            old_category=old_category,
                            new_category=result.get("category", old_category),
                            confidence=confidence, ai_tags=result.get("tags", []),
                            applied=False, reason=reason,
                        )
                    else:
                        new_cat = result.get("category", bm.category)
                        if new_cat and new_cat != bm.category:
                            if result.get("new_category") and new_cat not in self.category_manager.categories:
                                self.category_manager.add_category(new_cat)
                                new_categories.add(new_cat)
                            bm.category = new_cat
                            bm.ai_confidence = confidence
                            applied = True
                            applied_count += 1
                            reason = f"confidence {confidence:.0%}"

                        ai_tags = result.get("tags", [])
                        if ai_tags:
                            bm.ai_tags = [t.lower().strip() for t in ai_tags if t]

                        suggested_title = result.get("suggested_title")
                        if (suggested_title and suggested_title != bm.title
                                and suggested_title.lower() not in ("null", "none", "")):
                            bm.title = suggested_title
                            titles_changed += 1
                            log_title_improvement(
                                provider=provider_used,
                                model=result.get("_failover_model", client.last_model),
                                bookmark_id=bm.id, url=bm.url,
                                old_title=old_title, new_title=suggested_title,
                                applied=True,
                            )

                        reasoning = result.get("reasoning", "")
                        if reasoning and not bm.description:
                            bm.description = reasoning

                        bm.modified_at = datetime.now().isoformat()

                        log_categorize(
                            provider=provider_used,
                            model=result.get("_failover_model", client.last_model),
                            bookmark_id=bm.id, url=bm.url,
                            old_category=old_category,
                            new_category=bm.category,
                            confidence=confidence, ai_tags=result.get("tags", []),
                            suggested_title=result.get("suggested_title", ""),
                            summary=reasoning,
                            applied=applied, reason=reason,
                        )

                    if is_failover:
                        failover_count += 1

                    processed += 1
                    self.root.after(0, lambda b=bm, r=dict(result), a=applied, rsn=reason,
                                    pu=provider_used, fo=is_failover:
                                    _add_feed_entry(b, r, a, rsn, pu, fo))
                    self.root.after(0, lambda p=processed: [
                        stats_label.configure(text=f"{p} / {len(bookmarks)}"),
                        bar_fill.place(relwidth=p / len(bookmarks)),
                    ])

                # Save periodically
                self.bookmark_manager.save_bookmarks()

                import time
                if not cancelled[0] and end < len(bookmarks):
                    time.sleep(rate_delay)

            # Final save
            self.bookmark_manager.save_bookmarks()
            self.category_manager.save_categories()

            def _finish():
                if not dialog.winfo_exists():
                    return
                bar_fill.configure(bg=theme.accent_success)
                bar_fill.place(relwidth=1.0)
                cancel_btn.pack_forget()
                done_btn.pack(side=tk.RIGHT)

                summary = (
                    f"Done — {processed} processed, {applied_count} categorized"
                    f", {titles_changed} titles improved"
                )
                if failover_count:
                    summary += f", {failover_count} via failover"
                status_label.configure(text=summary, fg=theme.text_primary)
                self._refresh_all()

            self.root.after(0, _finish)

        threading.Thread(target=_worker, daemon=True).start()
