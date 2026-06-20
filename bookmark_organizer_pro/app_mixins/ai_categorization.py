"""AI categorization workflow with live activity feed and failover support."""

from __future__ import annotations

from datetime import datetime
import time
from tkinter import messagebox
from typing import List

from bookmark_organizer_pro.ai import create_failover_client
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.ai_audit_log import log_categorize, log_title_improvement
from bookmark_organizer_pro.services.ai_snapshot import create_snapshot
from bookmark_organizer_pro.ui.live_workflow import LiveWorkflowDialog


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
        """Run AI categorization with a live, drip-revealed activity feed."""
        dialog = LiveWorkflowDialog(
            self.root, title="AI Categorization", total=len(bookmarks),
            width=700, height=580,
        )

        def _worker():
            try:
                create_snapshot("ai_categorize", bookmarks)
            except Exception as snap_err:
                log.warning(f"AI snapshot failed (continuing): {snap_err}")
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
                if dialog.cancelled:
                    break

                end = min(start + batch_size, len(bookmarks))
                batch = bookmarks[start:end]
                bm_data = [{"url": bm.url, "title": bm.title} for bm in batch]

                dialog.set_status(
                    f"Processing {start + 1}–{end} of {len(bookmarks)}… "
                    f"({client.last_provider}/{client.last_model})"
                )

                try:
                    results = client.categorize_bookmarks(bm_data, categories, allow_new, suggest_tags)
                except Exception as exc:
                    log.warning(f"AI batch failed: {exc}")
                    err_msg = f"error: {str(exc)[:40]}"
                    for bm in batch:
                        dialog.add_result(status="error", title=(bm.title or bm.url), detail=err_msg)
                    processed += len(batch)
                    continue

                result_map = {r.get("url", ""): r for r in results}

                for bm in batch:
                    if dialog.cancelled:
                        break

                    result = result_map.get(bm.url, {})
                    confidence = result.get("confidence", 0)
                    is_failover = result.get("_failover", False)
                    provider_used = result.get("_failover_provider", client.last_provider)

                    old_category = bm.category
                    old_title = bm.title
                    old_tags = list(bm.ai_tags) if bm.ai_tags else []

                    # What the local default pattern engine predicts for this
                    # URL, captured before applying the AI result. Logged
                    # alongside the AI's choice so the defaults can be improved
                    # afterward (see ai_audit_log.analyze_for_default_improvements).
                    try:
                        pattern_prediction = self.category_manager.categorize_url(bm.url, old_title)
                    except Exception:
                        pattern_prediction = ""

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
                            old_title=old_title, old_tags=old_tags,
                            pattern_prediction=pattern_prediction,
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
                            old_title=old_title, old_tags=old_tags,
                            pattern_prediction=pattern_prediction,
                        )

                    if is_failover:
                        failover_count += 1

                    processed += 1

                    # Build the activity row (revealed one-at-a-time by the dialog).
                    new_cat = result.get("category", old_category)
                    tags = result.get("tags", [])
                    detail_parts = []
                    if applied and new_cat != old_category:
                        detail_parts.append(f"{old_category} → {new_cat}")
                    elif not applied:
                        detail_parts.append(f"kept: {old_category}")
                    detail_parts.append(f"{confidence:.0%}")
                    if is_failover:
                        detail_parts.append(f"via {provider_used}")
                    if tags:
                        detail_parts.append(f"tags: {', '.join(tags[:4])}")

                    status = "ok" if applied else ("warn" if reason.startswith("confidence") else "skip")
                    dialog.add_result(
                        status=status,
                        title=(bm.title or bm.url),
                        detail="  ·  ".join(detail_parts),
                    )

                # Save periodically
                self.bookmark_manager.save_bookmarks()

                if not dialog.cancelled and end < len(bookmarks):
                    time.sleep(rate_delay)

            # Final save
            self.bookmark_manager.save_bookmarks()
            self.category_manager.save_categories()

            summary = (
                f"Done — {processed} processed, {applied_count} categorized"
                f", {titles_changed} titles improved"
            )
            if failover_count:
                summary += f", {failover_count} via failover"
            dialog.signal_finish(summary)
            self.root.after(0, self._refresh_all)

        dialog.run(_worker)
