"""Natural-language → structured-query translator for smart collections.

The LLM is asked to fill a JSON schema (tags, exclude_tags, date filters,
content type, semantic seed). The result is validated and executed locally
against the BookmarkManager. We never let the model emit raw SQL.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, List, Optional, Sequence

from bookmark_organizer_pro.ai import AIConfigManager, create_ai_client
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark


SYSTEM_PROMPT = (
    "Translate the user's natural-language bookmark query into a strict JSON "
    "object that matches this schema. Output JSON only, no prose. Fields:\n"
    '  "tags_any":   list[str]      // bookmarks with ANY of these tags\n'
    '  "tags_all":   list[str]      // bookmarks with ALL of these tags\n'
    '  "exclude_tags": list[str]\n'
    '  "categories": list[str]\n'
    '  "domains":    list[str]      // hostname substrings\n'
    '  "date_after":  string|null   // ISO date, e.g. "2025-01-01"\n'
    '  "date_before": string|null\n'
    '  "unread_for_days": int|null  // bookmarks not visited in N days\n'
    '  "read_later":  bool|null\n'
    '  "content_type": string|null  // "article"|"video"|"code"|"paper"|"audio"|...\n'
    '  "language":    string|null\n'
    '  "semantic_seed": string|null // free-text used for vector search\n'
    '  "limit":       int           // 1-200, default 50\n'
    '  "sort":        string        // "recent"|"oldest"|"visited"|"score"\n'
)


@dataclass
class StructuredQuery:
    tags_any: List[str] = field(default_factory=list)
    tags_all: List[str] = field(default_factory=list)
    exclude_tags: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    date_after: Optional[str] = None
    date_before: Optional[str] = None
    unread_for_days: Optional[int] = None
    read_later: Optional[bool] = None
    content_type: Optional[str] = None
    language: Optional[str] = None
    semantic_seed: Optional[str] = None
    limit: int = 50
    sort: str = "recent"

    def to_dict(self) -> dict:
        return asdict(self)


class NLQueryTranslator:
    """Translate natural-language queries into a StructuredQuery."""

    def __init__(self, ai_config: AIConfigManager):
        self.ai_config = ai_config

    def translate(self, nl: str) -> StructuredQuery:
        nl = nl.strip()
        if not nl:
            return StructuredQuery()
        try:
            client = create_ai_client(self.ai_config)
            resp = client.complete(
                system=SYSTEM_PROMPT,
                prompt=f"USER QUERY: {nl}\n\nRespond with JSON only.",
                max_tokens=500,
                temperature=0.0,
            )
        except Exception as exc:
            log.warning(f"NL query translate failed: {exc}")
            return self._heuristic(nl)
        return self._parse(resp) or self._heuristic(nl)

    # ------------------------------------------------------------------
    def _parse(self, raw: str) -> Optional[StructuredQuery]:
        if not raw:
            return None
        text = raw.strip()
        if "```" in text:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if m:
                text = m.group(1)
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return None
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None

        def _list(v):
            if isinstance(v, list):
                return [str(x).strip() for x in v if str(x).strip()]
            if isinstance(v, str):
                return [s.strip() for s in v.split(",") if s.strip()]
            return []

        def _opt_str(v):
            if v is None:
                return None
            s = str(v).strip()
            return s or None

        def _opt_int(v):
            try:
                if v is None or v == "":
                    return None
                return int(v)
            except (TypeError, ValueError):
                return None

        def _opt_bool(v):
            if isinstance(v, bool):
                return v
            return None

        try:
            limit = max(1, min(200, int(data.get("limit", 50))))
        except (TypeError, ValueError):
            limit = 50
        sort = str(data.get("sort", "recent")).lower()
        if sort not in {"recent", "oldest", "visited", "score"}:
            sort = "recent"

        return StructuredQuery(
            tags_any=_list(data.get("tags_any")),
            tags_all=_list(data.get("tags_all")),
            exclude_tags=_list(data.get("exclude_tags")),
            categories=_list(data.get("categories")),
            domains=_list(data.get("domains")),
            date_after=_opt_str(data.get("date_after")),
            date_before=_opt_str(data.get("date_before")),
            unread_for_days=_opt_int(data.get("unread_for_days")),
            read_later=_opt_bool(data.get("read_later")),
            content_type=_opt_str(data.get("content_type")),
            language=_opt_str(data.get("language")),
            semantic_seed=_opt_str(data.get("semantic_seed")),
            limit=limit,
            sort=sort,
        )

    def _heuristic(self, nl: str) -> StructuredQuery:
        """Very small fallback when no AI is configured."""
        q = StructuredQuery()
        m = re.search(r"last\s+(\d+)\s+days?", nl, re.IGNORECASE)
        if m:
            days = int(m.group(1))
            q.date_after = (datetime.now() - timedelta(days=days)).date().isoformat()
        if re.search(r"\bunread\b|haven'?t\s+read", nl, re.IGNORECASE):
            q.read_later = True
        for word in ("video", "videos"):
            if re.search(rf"\b{word}\b", nl, re.IGNORECASE):
                q.content_type = "video"
                break
        if re.search(r"\bpaper(s)?\b", nl, re.IGNORECASE):
            q.content_type = "paper"
        q.semantic_seed = nl
        return q


def execute_query(query: StructuredQuery,
                  bookmarks: Sequence[Bookmark]) -> List[Bookmark]:
    """Run a StructuredQuery (without semantic ranking) over bookmarks."""

    def _date(b: Bookmark, attr: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(getattr(b, attr).replace("Z", "+00:00"))
        except Exception:
            return None

    after = None
    before = None
    if query.date_after:
        try:
            after = datetime.fromisoformat(query.date_after)
        except ValueError:
            after = None
    if query.date_before:
        try:
            before = datetime.fromisoformat(query.date_before)
        except ValueError:
            before = None

    tagset_lookup = lambda b: {t.lower() for t in (list(b.tags) + list(b.ai_tags))}
    tags_any = {t.lower() for t in query.tags_any}
    tags_all = {t.lower() for t in query.tags_all}
    excl = {t.lower() for t in query.exclude_tags}
    cats = {c.lower() for c in query.categories}
    domains = [d.lower() for d in query.domains]

    out: List[Bookmark] = []
    for bm in bookmarks:
        if cats and bm.category.lower() not in cats and bm.parent_category.lower() not in cats:
            continue
        if domains:
            d = bm.domain
            if not any(dom in d for dom in domains):
                continue
        bm_tags = tagset_lookup(bm)
        if tags_any and not (bm_tags & tags_any):
            continue
        if tags_all and not tags_all.issubset(bm_tags):
            continue
        if excl and (bm_tags & excl):
            continue
        if query.read_later is not None and bool(bm.read_later) != query.read_later:
            continue
        if query.content_type and bm.content_type and bm.content_type != query.content_type:
            continue
        if query.content_type and not bm.content_type:
            continue
        if query.language and bm.language and bm.language != query.language:
            continue
        if after:
            d = _date(bm, "created_at")
            if d and d.replace(tzinfo=None) < after:
                continue
        if before:
            d = _date(bm, "created_at")
            if d and d.replace(tzinfo=None) > before:
                continue
        if query.unread_for_days is not None:
            cutoff = datetime.now() - timedelta(days=query.unread_for_days)
            visited = _date(bm, "last_visited") if bm.last_visited else None
            if visited and visited.replace(tzinfo=None) > cutoff:
                continue
        out.append(bm)

    if query.sort == "oldest":
        out.sort(key=lambda b: b.created_at)
    elif query.sort == "visited":
        out.sort(key=lambda b: b.visit_count, reverse=True)
    else:
        out.sort(key=lambda b: b.created_at, reverse=True)
    return out[: query.limit]
