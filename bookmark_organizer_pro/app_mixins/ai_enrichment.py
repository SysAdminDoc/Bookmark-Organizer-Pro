"""AI tag and summary generation workflows with live activity feed."""

from __future__ import annotations

from datetime import datetime
import json
import time
from typing import List

from bookmark_organizer_pro.ai import create_failover_client
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.ai_audit_log import log_tag_suggestion, log_summary
from bookmark_organizer_pro.services.ai_snapshot import create_snapshot
from bookmark_organizer_pro.ui.live_workflow import LiveWorkflowDialog


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
        """Tag suggestion with batched API calls and a drip-revealed feed."""
        dialog = LiveWorkflowDialog(
            self.root, title="AI Tag Suggestions", total=len(bookmarks),
            width=680, height=520,
        )

        def _worker():
            try:
                create_snapshot("ai_tags", bookmarks)
            except Exception as snap_err:
                log.warning(f"AI snapshot failed (continuing): {snap_err}")
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
                if dialog.cancelled:
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
                    dialog.add_result(status="skip", title=(bm.title or bm.url),
                                      detail="(skipped — login/auth page)")

                if not real_batch:
                    continue

                bm_data = [{"url": bm.url, "title": bm.title} for bm in real_batch]

                dialog.set_status(f"Processing {start + 1}–{end} of {len(bookmarks)}…")

                try:
                    results = client.categorize_bookmarks(
                        bm_data, categories, allow_new=False, suggest_tags=True)
                    result_map = {r.get("url", ""): r for r in results}
                except Exception as exc:
                    log.warning(f"AI tag batch failed: {exc}")
                    for bm in real_batch:
                        processed += 1
                        dialog.add_result(status="error", title=(bm.title or bm.url),
                                          detail=f"error: {str(exc)[:40]}")
                    continue

                for bm in real_batch:
                    if dialog.cancelled:
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
                        detail = ", ".join(new_tags_added[:6]) if new_tags_added else ", ".join(ai_tags_clean[:6])
                        dialog.add_result(status="ok", title=(bm.title or bm.url),
                                          detail=detail, detail_color=dialog.theme.accent_primary)
                    else:
                        dialog.add_result(status="skip", title=(bm.title or bm.url),
                                          detail="no tags suggested")

                    processed += 1

                # Save periodically
                self.bookmark_manager.save_bookmarks()

                if not dialog.cancelled and end < len(bookmarks):
                    time.sleep(rate_delay)

            self.bookmark_manager.save_bookmarks()

            summary = f"Done — {tagged} tagged, {processed - tagged - skipped_urls} unchanged"
            if skipped_urls:
                summary += f", {skipped_urls} login/auth pages skipped"
            dialog.signal_finish(summary)
            self.root.after(0, self._refresh_all)

        dialog.run(_worker)

    def _ai_summarize(self):
        if not self._ensure_ai_ready("AI summaries"):
            return

        bookmarks = self._get_selected_bookmarks_for_action(
            "Select Bookmarks",
            "Select one or more bookmarks, then ask AI to write descriptions.",
        )
        if not bookmarks:
            return

        if len(bookmarks) > 10 and hasattr(self, "_show_toast"):
            self._show_toast("Summary generation started; larger selections can take longer", "info")

        self._run_ai_summaries_live(bookmarks)

    def _run_ai_summaries_live(self, bookmarks: List[Bookmark]):
        """Summary generation with batched calls and a drip-revealed feed."""
        dialog = LiveWorkflowDialog(
            self.root, title="AI Summaries", total=len(bookmarks),
            width=680, height=520,
        )

        def _worker():
            client = self._get_ai_client()
            if not client:
                dialog.set_status("AI client unavailable")
                dialog.signal_finish("Stopped — AI client unavailable")
                return

            provider = self.ai_config.get_provider()
            model = self.ai_config.get_model()
            batch_size = min(self.ai_config.get_batch_size(), 15)
            rate_delay = max(0.1, 60.0 / max(1, self.ai_config.get_rate_limit()))

            processed = 0
            updated = 0

            for start in range(0, len(bookmarks), batch_size):
                if dialog.cancelled:
                    break
                end = min(start + batch_size, len(bookmarks))
                batch = bookmarks[start:end]

                dialog.set_status(f"Processing {start + 1}–{end} of {len(bookmarks)}…")

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
                                dialog.add_result(status="ok", title=(bm.title or bm.url),
                                                  detail=desc[:80])
                            else:
                                dialog.add_result(status="skip", title=(bm.title or bm.url),
                                                  detail="no description returned")
                            processed += 1
                    else:
                        for bm in batch:
                            dialog.add_result(status="skip", title=(bm.title or bm.url),
                                              detail="invalid AI response")
                            processed += 1
                except Exception as exc:
                    log.warning(f"AI summary batch failed: {exc}")
                    for bm in batch:
                        dialog.add_result(status="error", title=(bm.title or bm.url),
                                          detail=f"error: {str(exc)[:40]}")
                        processed += 1

                self.bookmark_manager.save_bookmarks()
                if not dialog.cancelled and end < len(bookmarks):
                    time.sleep(rate_delay)

            self.bookmark_manager.save_bookmarks()
            dialog.signal_finish(f"Done — {updated} summaries generated")
            self.root.after(0, self._refresh_all)

        dialog.run(_worker)
