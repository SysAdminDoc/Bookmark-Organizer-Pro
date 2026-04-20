"""Content ingest pipeline.

At save time: extract main article text, derive reading time, language, and
content type locally (no LLM cost). Trafilatura is preferred when available
(SIGIR 2023 best F1); falls back to BeautifulSoup + heuristics otherwise.

Optional dependencies (lazy):
    trafilatura     primary extractor
    lingua          language detection (most accurate for short text)
    fasttext        fallback language detection
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from bookmark_organizer_pro.constants import EXTRACTED_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.url_utils import URLUtilities


WORDS_PER_MINUTE = 230  # Adult silent-reading consensus

CONTENT_TYPE_HINTS = {
    "video": ("youtube.com", "youtu.be", "vimeo.com", "twitch.tv", "tiktok.com"),
    "code": ("github.com", "gitlab.com", "bitbucket.org", "codeberg.org", "sr.ht"),
    "paper": ("arxiv.org", "ssrn.com", "biorxiv.org", "nature.com", "science.org",
              "acm.org", "ieee.org", "researchgate.net", "scholar.google"),
    "image": ("imgur.com", "flickr.com", "unsplash.com", "pexels.com",
              "deviantart.com", "behance.net"),
    "audio": ("spotify.com", "soundcloud.com", "podcasts.apple.com",
              "anchor.fm", "podbean.com"),
    "discussion": ("reddit.com", "news.ycombinator.com", "lobste.rs",
                   "discord.com", "stackexchange.com", "stackoverflow.com"),
    "social": ("twitter.com", "x.com", "mastodon.social", "bsky.app",
               "linkedin.com", "facebook.com", "instagram.com", "threads.net"),
}


@dataclass
class IngestResult:
    """Output of the ingest pipeline."""
    text: str = ""
    word_count: int = 0
    reading_time: int = 0
    language: str = ""
    content_type: str = ""
    title: str = ""
    description: str = ""
    extracted_path: str = ""
    success: bool = False
    error: str = ""

    def apply_to(self, bookmark: Bookmark) -> bool:
        """Apply the ingest result to a Bookmark in place. Returns True if
        any field changed."""
        changed = False
        if self.word_count and bookmark.word_count != self.word_count:
            bookmark.word_count = self.word_count
            changed = True
        if self.reading_time and bookmark.reading_time != self.reading_time:
            bookmark.reading_time = self.reading_time
            changed = True
        if self.language and not bookmark.language:
            bookmark.language = self.language
            changed = True
        if self.content_type and not bookmark.content_type:
            bookmark.content_type = self.content_type
            changed = True
        if self.title and (not bookmark.title or bookmark.title == bookmark.url):
            bookmark.title = self.title[:500]
            changed = True
        if self.description and not bookmark.description:
            bookmark.description = self.description[:1000]
            changed = True
        if self.extracted_path and not bookmark.extracted_text_path:
            bookmark.extracted_text_path = self.extracted_path
            changed = True
        return changed


def _try_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _detect_content_type_from_url(url: str) -> str:
    domain = ""
    try:
        from urllib.parse import urlparse
        domain = (urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""
    for ctype, hosts in CONTENT_TYPE_HINTS.items():
        if any(domain == h or domain.endswith("." + h) for h in hosts):
            return ctype
    return ""


def _detect_content_type_from_text(text: str, word_count: int) -> str:
    if word_count > 500:
        if re.search(r"```|def |function |class |import |#include", text):
            return "tutorial"
        if word_count > 2000:
            return "longform"
        return "article"
    if word_count > 100:
        return "snippet"
    return "link"


def _detect_language(text: str) -> str:
    """Try lingua first, then fasttext, then a fragile heuristic."""
    if not text or len(text) < 20:
        return ""

    lingua = _try_import("lingua")
    if lingua is not None:
        try:
            detector = getattr(lingua, "LanguageDetectorBuilder").from_all_languages().build()
            result = detector.detect_language_of(text[:2000])
            if result is not None:
                return getattr(result, "iso_code_639_1").name.lower()
        except Exception as exc:
            log.debug(f"lingua detection failed: {exc}")

    ftld = _try_import("fasttext_langdetect")
    if ftld is not None:
        try:
            return str(ftld.detect(text[:2000])["lang"])
        except Exception:
            pass

    # Heuristic: ASCII ratio
    ascii_count = sum(1 for c in text[:1000] if ord(c) < 128)
    return "en" if ascii_count > 800 else ""


def _trafilatura_extract(html: str, url: str) -> Optional[Dict[str, str]]:
    traf = _try_import("trafilatura")
    if traf is None:
        return None
    try:
        text = traf.extract(html, url=url, favor_recall=True,
                            include_comments=False, include_tables=False)
        if not text:
            return None
        meta = traf.extract_metadata(html, default_url=url)
        return {
            "text": text,
            "title": getattr(meta, "title", "") or "",
            "description": getattr(meta, "description", "") or "",
        }
    except Exception as exc:
        log.debug(f"trafilatura extract failed: {exc}")
        return None


def _bs4_fallback(html: str) -> Optional[Dict[str, str]]:
    bs4 = _try_import("bs4")
    if bs4 is None:
        return None
    try:
        soup = bs4.BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""
        desc = ""
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            desc = meta["content"]
        return {"text": text, "title": title, "description": desc}
    except Exception as exc:
        log.debug(f"bs4 fallback failed: {exc}")
        return None


def _fetch_html(url: str, timeout: int = 15) -> Optional[str]:
    if not URLUtilities._is_safe_url(url):
        return None
    requests = _try_import("requests")
    if requests is None:
        return None
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (BookmarkOrganizerPro/6.0)"},
            timeout=timeout,
            allow_redirects=True,
            stream=True,
        )
    except Exception as exc:
        log.debug(f"fetch failed for {url}: {exc}")
        return None

    try:
        ctype = resp.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if ctype and not (ctype.startswith("text/") or ctype == "application/xhtml+xml"):
            return None
        # Cap at 4MB to bound memory
        chunks = bytearray()
        for chunk in resp.iter_content(chunk_size=16384):
            if chunk:
                chunks.extend(chunk)
                if len(chunks) > 4_000_000:
                    break
        return chunks.decode(resp.encoding or "utf-8", errors="replace")
    finally:
        try:
            resp.close()
        except Exception:
            pass


def _store_extracted(bookmark_id: int, text: str) -> str:
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    path = EXTRACTED_DIR / f"{bookmark_id}.txt"
    try:
        path.write_text(text, encoding="utf-8")
        return str(path)
    except Exception as exc:
        log.warning(f"Could not write extracted text: {exc}")
        return ""


class ContentIngestor:
    """Coordinates HTML fetch → extract → derive metrics → persist."""

    def ingest_url(self, url: str, bookmark_id: Optional[int] = None,
                   html: Optional[str] = None,
                   store_text: bool = True) -> IngestResult:
        result = IngestResult()
        if html is None:
            html = _fetch_html(url)
        if not html:
            result.error = "Could not fetch page"
            return result

        extracted = _trafilatura_extract(html, url) or _bs4_fallback(html)
        if not extracted:
            result.error = "No extraction backend available"
            return result

        text = extracted.get("text", "").strip()
        result.title = extracted.get("title", "").strip()
        result.description = extracted.get("description", "").strip()
        result.text = text
        result.word_count = len(text.split()) if text else 0
        result.reading_time = max(0, result.word_count // WORDS_PER_MINUTE)
        result.language = _detect_language(text)
        result.content_type = (
            _detect_content_type_from_url(url)
            or _detect_content_type_from_text(text, result.word_count)
        )
        result.success = True

        if store_text and bookmark_id is not None and text:
            result.extracted_path = _store_extracted(bookmark_id, text)
        return result

    def ingest_bookmark(self, bookmark: Bookmark, store_text: bool = True) -> IngestResult:
        return self.ingest_url(bookmark.url, bookmark.id, store_text=store_text)
