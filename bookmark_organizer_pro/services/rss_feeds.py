"""RSS / Atom feed ingestor with per-feed AI tagging rules.

Each registered feed has:
    * fetch URL
    * default tags (always applied)
    * default category
    * AI tagging mode: PREDEFINED | EXISTING | AUTO_GENERATE | DISABLED

Solves the open issues `karakeep #833` and `linkwarden #956`: a static-tag
layer that AI tagging adds to rather than replaces.
"""

from __future__ import annotations

from copy import deepcopy
import re
import threading
import xml.etree.ElementTree as ET


_FORBIDDEN_XML_DECLARATION = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)


def _stdlib_safe_xml_fromstring(text):
    """Fail closed on every DTD/entity declaration before stdlib XML parsing."""
    if _FORBIDDEN_XML_DECLARATION.search(text):
        raise ValueError("RSS XML DTD and entity declarations are not allowed")
    return ET.fromstring(text)


try:
    from defusedxml.ElementTree import fromstring as _xml_fromstring
except ImportError:
    _xml_fromstring = _stdlib_safe_xml_fromstring
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.parse import urljoin

from bookmark_organizer_pro.constants import FEEDS_FILE
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.job_ledger import JobLedger
from bookmark_organizer_pro.services.atomic_document_store import (
    AtomicDocumentStore,
    require_list_document,
)
from bookmark_organizer_pro.url_utils import URLUtilities


AI_MODES = {"PREDEFINED", "EXISTING", "AUTO_GENERATE", "DISABLED"}
_XML_BASE = "{http://www.w3.org/XML/1998/namespace}base"


@dataclass
class FeedConfig:
    id: str
    url: str
    name: str
    default_tags: List[str] = field(default_factory=list)
    default_category: str = ""
    ai_mode: str = "DISABLED"  # one of AI_MODES
    last_fetched: str = ""
    last_seen_guids: List[str] = field(default_factory=list)
    enabled: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FeedItem:
    title: str
    link: str
    summary: str = ""
    published: str = ""
    guid: str = ""


class FeedRegistry:
    """Persistent registry of RSS/Atom feeds with their tagging rules."""

    def __init__(self, filepath: Path = FEEDS_FILE):
        self.filepath = Path(filepath)
        self._lock = threading.RLock()
        self._store = AtomicDocumentStore(
            self.filepath,
            schema="bookmark-organizer-pro/rss-feeds",
            default_factory=list,
            validator=require_list_document,
        )
        self._revision = 0
        self._feeds: Dict[str, FeedConfig] = {}
        self._committed_feeds: Dict[str, FeedConfig] = {}
        self._load()

    @property
    def storage_status(self):
        return self._store.status

    def _load(self):
        data = self._store.load()
        self._revision = self._store.revision
        with self._lock:
            for d in data if isinstance(data, list) else []:
                try:
                    cfg = FeedConfig(**d)
                    if cfg.ai_mode not in AI_MODES:
                        cfg.ai_mode = "DISABLED"
                    self._feeds[cfg.id] = cfg
                except TypeError:
                    continue
            self._committed_feeds = deepcopy(self._feeds)

    def _save(self):
        with self._lock:
            payload = [f.to_dict() for f in self._feeds.values()]
            try:
                revision = self._store.save(payload, expected_revision=self._revision)
            except Exception:
                self._feeds = deepcopy(self._committed_feeds)
                raise
            self._revision = revision
            self._committed_feeds = deepcopy(self._feeds)

    def add(
        self,
        url: str,
        name: str = "",
        default_tags: Optional[List[str]] = None,
        default_category: str = "",
        ai_mode: str = "DISABLED",
    ) -> FeedConfig:
        if not URLUtilities._is_safe_url(url):
            raise ValueError("Unsafe or unsupported feed URL")
        if ai_mode not in AI_MODES:
            raise ValueError(f"Invalid feed AI mode: {ai_mode}")
        import uuid

        cfg = FeedConfig(
            id=uuid.uuid4().hex,
            url=url,
            name=name or url,
            default_tags=list(default_tags or []),
            default_category=default_category,
            ai_mode=ai_mode,
        )
        with self._lock:
            self._feeds[cfg.id] = cfg
            self._save()
            return deepcopy(cfg)

    def remove(self, feed_id: str) -> bool:
        with self._lock:
            if feed_id not in self._feeds:
                return False
            del self._feeds[feed_id]
            self._save()
            return True

    def update(self, feed_id: str, **kwargs) -> Optional[FeedConfig]:
        with self._lock:
            cfg = self._feeds.get(feed_id)
            if not cfg:
                return None
            candidate = deepcopy(cfg)
            for key, value in kwargs.items():
                if key == "id":
                    if value != feed_id:
                        raise ValueError("Feed IDs are immutable")
                    continue
                if not hasattr(candidate, key):
                    raise ValueError(f"Unknown feed field: {key}")
                setattr(candidate, key, value)
            if candidate.id != feed_id:
                raise ValueError("Feed IDs are immutable")
            if not URLUtilities._is_safe_url(candidate.url):
                raise ValueError("Unsafe or unsupported feed URL")
            if candidate.ai_mode not in AI_MODES:
                raise ValueError(f"Invalid feed AI mode: {candidate.ai_mode}")
            self._feeds[feed_id] = candidate
            self._save()
            return deepcopy(candidate)

    def list_feeds(self) -> List[FeedConfig]:
        with self._lock:
            return deepcopy(list(self._feeds.values()))

    def get(self, feed_id: str) -> Optional[FeedConfig]:
        with self._lock:
            cfg = self._feeds.get(feed_id)
            return deepcopy(cfg) if cfg is not None else None


def _element_base(element: ET.Element, parent_base: str) -> str:
    declared = (element.get(_XML_BASE) or "").strip()
    return urljoin(parent_base, declared) if declared else parent_base


def _resolve_link(element: ET.Element | None, raw_link: str, parent_base: str) -> str:
    link = raw_link.strip()
    if not link:
        return ""
    return urljoin(_element_base(element, parent_base) if element is not None else parent_base, link)


def parse_feed(xml_text: str, base_url: str = "") -> List[FeedItem]:
    """Best-effort RSS 2.0 + Atom 1.0 parser using stdlib."""
    items: List[FeedItem] = []
    try:
        root = _xml_fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning(f"Feed parse failed: {exc}")
        return items

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "content": "http://purl.org/rss/1.0/modules/content/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    root_base = _element_base(root, base_url)

    # RSS 2.0. XML Base cascades from document to channel, item, and link.
    rss_entries: list[tuple[ET.Element, str]] = []
    channels = root.findall(".//channel")
    for channel in channels:
        channel_base = _element_base(channel, root_base)
        rss_entries.extend((entry, channel_base) for entry in channel.findall("item"))
    if not channels:
        rss_entries.extend((entry, root_base) for entry in root.findall(".//item"))
    for entry, channel_base in rss_entries:
        entry_base = _element_base(entry, channel_base)
        link_element = entry.find("link")
        link = _resolve_link(
            link_element,
            link_element.text if link_element is not None and link_element.text else "",
            entry_base,
        )
        items.append(
            FeedItem(
                title=(entry.findtext("title") or "").strip(),
                link=link,
                summary=(entry.findtext("description") or "").strip()[:500],
                published=(entry.findtext("pubDate") or entry.findtext("dc:date", "", ns) or "").strip(),
                guid=(entry.findtext("guid") or link).strip(),
            )
        )

    # Atom 1.0
    for entry in root.findall("atom:entry", ns):
        entry_base = _element_base(entry, root_base)
        link_el = entry.find("atom:link", ns)
        href = _resolve_link(
            link_el,
            (link_el.get("href") or "") if link_el is not None else "",
            entry_base,
        )
        items.append(
            FeedItem(
                title=(entry.findtext("atom:title", "", ns) or "").strip(),
                link=href,
                summary=(entry.findtext("atom:summary", "", ns) or "").strip()[:500],
                published=(entry.findtext("atom:updated", "", ns) or "").strip(),
                guid=(entry.findtext("atom:id", "", ns) or href).strip(),
            )
        )
    return items


class FeedIngestor:
    """Fetch each feed, materialize new items into bookmarks, and apply
    static + AI tags according to the per-feed mode."""

    def __init__(
        self,
        registry: FeedRegistry,
        add_bookmark_callable: Callable[[Bookmark], Optional[Bookmark]],
        ai_tagger: Optional[Callable[[Bookmark, str], List[str]]] = None,
        existing_tags_provider: Optional[Callable[[], List[str]]] = None,
        job_ledger: JobLedger | None = None,
    ):
        self.registry = registry
        self.add_bookmark = add_bookmark_callable
        self.ai_tagger = ai_tagger
        self.existing_tags_provider = existing_tags_provider
        self.job_ledger = job_ledger or JobLedger()

    def fetch_all(self) -> Dict[str, int]:
        """Fetch every enabled feed; return {feed_id: new_count}."""
        out: Dict[str, int] = {}
        for cfg in self.registry.list_feeds():
            if not cfg.enabled:
                continue
            try:
                out[cfg.id] = self.fetch_one(cfg.id)
            except Exception as exc:
                log.warning(f"Feed {cfg.name} failed: {exc}")
                out[cfg.id] = -1
        return out

    def fetch_one(self, feed_id: str) -> int:
        cfg = self.registry.get(feed_id)
        job = self.job_ledger.start(
            "rss",
            url_or_domain=cfg.url if cfg else "",
            backend="requests",
        )
        try:
            added = self._fetch_one(feed_id)
        except Exception as exc:
            job.fail(exc, retryable=True)
            raise
        job.succeed()
        return added

    def _fetch_one(self, feed_id: str) -> int:
        cfg = self.registry.get(feed_id)
        if cfg is None:
            raise KeyError(f"Feed not found: {feed_id}")
        if not URLUtilities._is_safe_url(cfg.url):
            raise ValueError("Unsafe or unsupported feed URL")
        from bookmark_organizer_pro.services.egress import public_egress as requests

        resp = requests.get(
            cfg.url,
            timeout=20,
            headers={"User-Agent": "BookmarkOrganizerPro/6.0"},
            allow_redirects=True,
        )
        resp.raise_for_status()
        final_url = str(getattr(resp, "url", "") or cfg.url)
        content_location = str(resp.headers.get("Content-Location", "") or "").strip()
        response_base = urljoin(final_url, content_location) if content_location else final_url
        items = parse_feed(resp.text, base_url=response_base)
        seen = set(cfg.last_seen_guids or [])
        added = 0
        new_guids: List[str] = []
        for item in items:
            if not item.link or not URLUtilities._is_safe_url(item.link):
                continue
            guid = item.guid or item.link
            if guid in seen:
                continue
            new_guids.append(guid)
            tags = list(cfg.default_tags)
            if cfg.ai_mode != "DISABLED" and self.ai_tagger is not None:
                ai_tags = self._safe_ai_tag(item, cfg)
                for t in ai_tags:
                    if t and t.lower() not in {x.lower() for x in tags}:
                        tags.append(t)
            try:
                bookmark = Bookmark(
                    id=None,
                    url=item.link,
                    title=item.title or item.link,
                    description=item.summary,
                    category=cfg.default_category or "Uncategorized / Needs Review",
                    tags=tags,
                    source_file=f"feed:{cfg.name}",
                )
            except ValueError:
                continue
            result = self.add_bookmark(bookmark)
            if result is not None:
                added += 1

        # Cap memory of seen guids; keep most recent ~500
        cfg.last_seen_guids = (new_guids + cfg.last_seen_guids)[:500]
        cfg.last_fetched = datetime.now().isoformat()
        self.registry.update(cfg.id, last_seen_guids=cfg.last_seen_guids, last_fetched=cfg.last_fetched)
        return added

    def _safe_ai_tag(self, item: FeedItem, cfg: FeedConfig) -> List[str]:
        if self.ai_tagger is None:
            return []
        try:
            existing = []
            if cfg.ai_mode == "EXISTING" and self.existing_tags_provider is not None:
                existing = list(self.existing_tags_provider())
            elif cfg.ai_mode == "PREDEFINED":
                existing = list(cfg.default_tags)
            tags = self.ai_tagger(item, cfg.ai_mode)  # signature flexible
            if cfg.ai_mode == "EXISTING" and existing:
                allowed = {t.lower() for t in existing}
                tags = [t for t in tags if t.lower() in allowed]
            return tags
        except Exception as exc:
            log.debug(f"AI tagging skipped: {exc}")
            return []
