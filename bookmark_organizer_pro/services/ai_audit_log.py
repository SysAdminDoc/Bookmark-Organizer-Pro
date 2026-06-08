"""Structured AI audit log for bookmark modifications.

Every AI action on a bookmark is recorded as a JSON line in
~/.bookmark_organizer/logs/ai_audit.jsonl

Each entry captures: what changed, what the AI suggested, what was applied,
the provider/model used, and the bookmark before/after state. This log is
designed to be machine-readable so a coding agent can review it and extract
patterns for improving the categorization engine.

Format per line (JSONL):
{
  "timestamp": "2026-06-05T18:30:00",
  "action": "categorize|tag|title|summarize|enrich",
  "provider": "ollama",
  "model": "qwen3.5",
  "bookmark_id": 12345,
  "url": "https://example.com",
  "before": { "category": "Uncategorized", "title": "...", "tags": [...] },
  "after":  { "category": "Technology", "title": "...", "tags": [...] },
  "ai_response": { "category": "Technology", "confidence": 0.92, "tags": [...], "summary": "..." },
  "applied": true,
  "reason": "confidence 0.92 >= threshold 0.5"
}
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from bookmark_organizer_pro.constants import LOGS_DIR
from bookmark_organizer_pro.logging_config import log

AI_AUDIT_FILE = LOGS_DIR / "ai_audit.jsonl"
_write_lock = threading.Lock()

# Canonical "no confident default matched" category.
UNCATEGORIZED = "Uncategorized / Needs Review"

# Below this AI confidence we don't treat the AI's category as a trustworthy
# signal for evaluating/improving the shipped defaults.
DEFAULT_SIGNAL_MIN_CONFIDENCE = 0.6


def _ensure_log_dir():
    AI_AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)


def _classify_agreement(pattern_prediction: str, ai_category: str,
                        confidence: float) -> str:
    """Compare the local default-pattern prediction with the AI's category.

    Returns one of:
    - "low_confidence": AI confidence too low to learn from.
    - "miss":    defaults produced no confident match but the AI did — the
                 strongest signal for a NEW default pattern to add.
    - "confirm": defaults and AI agree — validates an existing pattern.
    - "disagree": defaults matched a *different* category than the AI — a
                 candidate to FIX (or an AI error worth a human glance).
    """
    pred = (pattern_prediction or "").strip()
    ai = (ai_category or "").strip()
    if not ai or confidence < DEFAULT_SIGNAL_MIN_CONFIDENCE:
        return "low_confidence"
    if not pred or pred == UNCATEGORIZED:
        return "miss"
    if pred == ai:
        return "confirm"
    return "disagree"


def log_ai_action(
    action: str,
    provider: str,
    model: str,
    bookmark_id: int,
    url: str,
    before: Dict[str, Any],
    after: Dict[str, Any],
    ai_response: Dict[str, Any],
    applied: bool = True,
    reason: str = "",
    extra: Optional[Dict[str, Any]] = None,
):
    """Write one structured AI audit entry.

    ``extra`` is merged into the top-level entry (used to attach the default-
    pattern ``evaluation`` block on categorize actions).
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "provider": provider,
        "model": model,
        "bookmark_id": bookmark_id,
        "url": url[:500],
        "before": before,
        "after": after,
        "ai_response": ai_response,
        "applied": applied,
        "reason": reason,
    }
    if extra:
        entry.update(extra)

    try:
        _ensure_log_dir()
        line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
        with _write_lock:
            with open(AI_AUDIT_FILE, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception as exc:
        log.warning(f"Failed to write AI audit log: {exc}")


def log_categorize(
    provider: str, model: str, bookmark_id: int, url: str,
    old_category: str, new_category: str,
    confidence: float, ai_tags: List[str],
    suggested_title: str = "", summary: str = "",
    applied: bool = True, reason: str = "",
    old_title: str = "", old_tags: Optional[List[str]] = None,
    pattern_prediction: Optional[str] = None,
):
    """Log an AI categorization action.

    ``pattern_prediction`` is what the local default pattern engine
    (``CategoryManager.categorize_url``) predicted for this URL *before* the AI
    ran. Recording it lets an agent compare the shipped defaults against the AI
    and mine concrete improvements (see ``analyze_for_default_improvements``):
    "miss" → add a default pattern, "disagree" → fix one, "confirm" → validated.
    """
    from urllib.parse import urlparse
    domain = ""
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
    except Exception:
        pass
    before: Dict[str, Any] = {"category": old_category}
    if old_title:
        before["title"] = old_title[:200]
    if old_tags:
        before["tags"] = old_tags
    if domain:
        before["domain"] = domain

    extra: Optional[Dict[str, Any]] = None
    if pattern_prediction is not None:
        extra = {
            "evaluation": {
                "domain": domain,
                "pattern_prediction": pattern_prediction,
                "pattern_matched": bool(
                    pattern_prediction and pattern_prediction != UNCATEGORIZED
                ),
                "ai_category": new_category,
                "ai_confidence": confidence,
                "agreement": _classify_agreement(pattern_prediction, new_category, confidence),
            }
        }

    log_ai_action(
        action="categorize",
        provider=provider, model=model,
        bookmark_id=bookmark_id, url=url,
        before=before,
        after={"category": new_category},
        ai_response={
            "category": new_category,
            "confidence": confidence,
            "tags": ai_tags,
            "suggested_title": suggested_title,
            "summary": summary,
        },
        applied=applied, reason=reason,
        extra=extra,
    )


def log_tag_suggestion(
    provider: str, model: str, bookmark_id: int, url: str,
    old_tags: List[str], new_tags: List[str], ai_tags: List[str],
    applied: bool = True,
):
    """Log AI tag suggestions."""
    from urllib.parse import urlparse
    domain = ""
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
    except Exception:
        pass
    before: Dict[str, Any] = {"tags": old_tags}
    if domain:
        before["domain"] = domain
    log_ai_action(
        action="tag",
        provider=provider, model=model,
        bookmark_id=bookmark_id, url=url,
        before=before,
        after={"tags": new_tags},
        ai_response={"suggested_tags": ai_tags},
        applied=applied,
    )


def log_title_improvement(
    provider: str, model: str, bookmark_id: int, url: str,
    old_title: str, new_title: str,
    applied: bool = True,
):
    """Log AI title improvement."""
    log_ai_action(
        action="title",
        provider=provider, model=model,
        bookmark_id=bookmark_id, url=url,
        before={"title": old_title},
        after={"title": new_title},
        ai_response={"suggested_title": new_title},
        applied=applied,
    )


def log_summary(
    provider: str, model: str, bookmark_id: int, url: str,
    summary: str, applied: bool = True,
):
    """Log AI summary generation."""
    log_ai_action(
        action="summarize",
        provider=provider, model=model,
        bookmark_id=bookmark_id, url=url,
        before={}, after={"description": summary[:200]},
        ai_response={"summary": summary},
        applied=applied,
    )


def log_batch_result(
    provider: str, model: str, bookmark_id: int, url: str,
    old_category: str, old_tags: List[str], old_title: str,
    result: Dict[str, Any], applied: bool = True, reason: str = "",
):
    """Log a batch AI processing result (categorize + tags + summary in one call)."""
    log_ai_action(
        action="enrich",
        provider=provider, model=model,
        bookmark_id=bookmark_id, url=url,
        before={"category": old_category, "tags": old_tags, "title": old_title},
        after={
            "category": result.get("category", old_category),
            "tags": result.get("tags", old_tags),
            "summary": (result.get("summary") or "")[:200],
        },
        ai_response=result,
        applied=applied, reason=reason,
    )


def read_audit_log(limit: int = 1000) -> List[Dict]:
    """Read the most recent audit log entries."""
    if not AI_AUDIT_FILE.exists():
        return []
    entries = []
    try:
        with open(AI_AUDIT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return []
    return entries[-limit:]


# Domains whose true category can't be inferred from individual bookmarked
# URLs. Search engines / general portals serve every topic, so the AI ends up
# labeling the *domain* by the content of whatever pages happened to be
# bookmarked (e.g. adult image-search results on a search engine → "Adult
# Content"). Aggregated AI votes for these are noise — never auto-reclassify.
_GENERAL_PURPOSE_DOMAINS = {
    "google.com", "google.co.uk", "bing.com", "yandex.com", "yandex.ru",
    "baidu.com", "duckduckgo.com", "yahoo.com", "ask.com", "ecosia.org",
    "startpage.com", "search.brave.com", "archive.org", "web.archive.org",
    "translate.google.com", "scholar.google.com", "pinterest.com",
}

# Reclassifying a previously-benign domain INTO one of these warrants explicit
# human sign-off unless agreement is essentially unanimous.
_SENSITIVE_TARGET_CATEGORIES = {"Adult Content"}


def _suspect_recategorization(domain: str, ai_category: str,
                              default_category: str, share: float):
    """Flag domain-level AI verdicts that look like aggregation artifacts.

    Returns ``(is_suspect, reason)``. Suspect candidates should never be applied
    to the defaults automatically — they need a human glance (this is what
    caught ``yandex.com → Adult Content`` in practice).
    """
    domain = (domain or "").lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if domain in _GENERAL_PURPOSE_DOMAINS:
        return True, ("general-purpose search/portal domain - per-URL content "
                      "misleads domain-level aggregation")
    if (ai_category in _SENSITIVE_TARGET_CATEGORIES
            and default_category not in _SENSITIVE_TARGET_CATEGORIES
            and share < 0.95):
        return True, (f"reclassifies into sensitive category '{ai_category}' "
                      f"below unanimous agreement (share={share:.0%})")
    return False, ""


def analyze_for_default_improvements(
    min_confidence: float = 0.7,
    min_support: int = 2,
    limit: int = 500000,
) -> Dict[str, Any]:
    """Mine the audit log for concrete improvements to the shipped defaults.

    Aggregates ``categorize`` entries (that carry an ``evaluation`` block) by
    domain and, for each domain, finds the dominant high-confidence AI category
    and how the local default pattern engine compared. Produces three buckets,
    each sorted by support (number of confident samples):

    - ``add_patterns``:   domains the defaults never matched but the AI
                          categorized confidently and consistently. Each is a
                          ready-to-add ``domain:<domain>`` rule for the named
                          category in ``core/default_categories.json``.
    - ``review_patterns``: domains where an existing default matched a category
                          but the AI consistently disagrees — candidates to fix
                          (or AI noise worth a human glance).
    - ``confirmed``:      domains where defaults and the AI agree (the defaults
                          are pulling their weight).

    Args:
        min_confidence: ignore AI categorizations below this confidence.
        min_support: require at least this many confident samples per (domain,
            category) before recommending a change.

    Returns a JSON-serializable dict; intended to be read by a coding agent (or
    dumped to review) after a large categorization run.
    """
    entries = read_audit_log(limit=limit)

    # domain -> {category -> [confidences]}, plus the default predictions seen.
    by_domain: Dict[str, Dict[str, List[float]]] = {}
    domain_predictions: Dict[str, Dict[str, int]] = {}
    total_evaluated = 0

    for e in entries:
        if e.get("action") != "categorize":
            continue
        ev = e.get("evaluation")
        if not isinstance(ev, dict):
            continue
        domain = (ev.get("domain") or "").strip().lower()
        ai_cat = (ev.get("ai_category") or "").strip()
        conf = ev.get("ai_confidence", 0) or 0
        if not domain or not ai_cat:
            continue
        total_evaluated += 1
        if conf < min_confidence:
            continue
        by_domain.setdefault(domain, {}).setdefault(ai_cat, []).append(float(conf))
        pred = (ev.get("pattern_prediction") or UNCATEGORIZED).strip() or UNCATEGORIZED
        domain_predictions.setdefault(domain, {})
        domain_predictions[domain][pred] = domain_predictions[domain].get(pred, 0) + 1

    add_patterns: List[Dict[str, Any]] = []
    review_patterns: List[Dict[str, Any]] = []
    confirmed: List[Dict[str, Any]] = []

    for domain, cats in by_domain.items():
        # Dominant AI category for this domain (most confident samples).
        top_cat, confs = max(cats.items(), key=lambda kv: (len(kv[1]), sum(kv[1])))
        support = len(confs)
        if support < min_support:
            continue
        avg_conf = round(sum(confs) / support, 3)
        # Concentration: fraction of this domain's confident votes that went to
        # the dominant category. Low share ⇒ multi-topic domain (youtube/reddit)
        # whose category can't be set by a single domain rule.
        total_votes = sum(len(c) for c in cats.values())
        share = round(support / total_votes, 3) if total_votes else 0.0

        preds = domain_predictions.get(domain, {})
        # The default the engine most often produced for this domain.
        default_pred = max(preds.items(), key=lambda kv: kv[1])[0] if preds else UNCATEGORIZED
        ever_matched = any(p != UNCATEGORIZED for p in preds)

        suspect, suspect_reason = _suspect_recategorization(
            domain, top_cat, default_pred, share)

        record = {
            "domain": domain,
            "suggested_category": top_cat,
            "support": support,
            "share": share,
            "avg_confidence": avg_conf,
            "current_default": default_pred,
            "suggested_pattern": f"domain:{domain}",
            "suspect": suspect,
            "suspect_reason": suspect_reason,
        }

        if not ever_matched:
            add_patterns.append(record)          # defaults have nothing → add
        elif default_pred != top_cat:
            review_patterns.append(record)        # defaults disagree → fix
        else:
            confirmed.append(record)              # defaults agree → validated

    # Suspect candidates last within each bucket so the safe, high-signal ones
    # surface first.
    add_patterns.sort(key=lambda r: (r["suspect"], -r["support"], -r["avg_confidence"]))
    review_patterns.sort(key=lambda r: (r["suspect"], -r["support"], -r["avg_confidence"]))
    confirmed.sort(key=lambda r: -r["support"])

    suspect_count = sum(1 for r in (add_patterns + review_patterns) if r["suspect"])

    return {
        "params": {"min_confidence": min_confidence, "min_support": min_support},
        "categorize_entries_with_evaluation": total_evaluated,
        "unique_domains": len(by_domain),
        "summary": {
            "add_patterns": len(add_patterns),
            "review_patterns": len(review_patterns),
            "confirmed": len(confirmed),
            "suspect_flagged": suspect_count,
        },
        "add_patterns": add_patterns,
        "review_patterns": review_patterns,
        "confirmed": confirmed,
    }


def get_audit_stats() -> Dict[str, Any]:
    """Get summary statistics from the audit log."""
    entries = read_audit_log(limit=100000)
    if not entries:
        return {"total": 0}

    actions = {}
    providers = {}
    categories_changed = {}

    for e in entries:
        action = e.get("action", "unknown")
        actions[action] = actions.get(action, 0) + 1
        prov = e.get("provider", "unknown")
        providers[prov] = providers.get(prov, 0) + 1

        if action == "categorize" and e.get("applied"):
            new_cat = e.get("after", {}).get("category", "")
            if new_cat:
                categories_changed[new_cat] = categories_changed.get(new_cat, 0) + 1

    return {
        "total": len(entries),
        "by_action": actions,
        "by_provider": providers,
        "top_categories": dict(sorted(categories_changed.items(), key=lambda x: -x[1])[:20]),
        "first": entries[0].get("timestamp", "") if entries else "",
        "last": entries[-1].get("timestamp", "") if entries else "",
    }
