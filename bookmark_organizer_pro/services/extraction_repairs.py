"""Declarative repairs for sites the default extractor reads badly.

A generic extractor gets most pages right and a handful badly: a forum thread
that keeps only the first post, a docs page whose sidebar drowns the body, a
news site that returns the cookie banner. The fix has to stay data, not code,
because this content is untrusted and the app already refuses to run scripts
from it or reach new origins during extraction.

A repair therefore does exactly two things to HTML the app has ALREADY
fetched: pick the element that holds the article, and drop elements that are
known boilerplate. Selectors come from the same allowlist the structured
templates use, everything is size and time bounded, and a rule that fails to
improve the page leaves the default output untouched.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.services.extraction_templates import (
    _clamp_int,
    _clean_value,
    _read_template_payload,
    _safe_domain,
    _safe_selector,
    _try_import,
    _url_domain,
)

MAX_REPAIRS = 50
MAX_REMOVE_SELECTORS = 20
MAX_OUTPUT_CHARS = 400_000
MAX_INPUT_CHARS = 4_000_000
REPAIR_TIME_BUDGET_SECONDS = 5.0
MIN_REPAIRED_CHARS = 40

REPAIRS_FILE = DATA_DIR / "extraction_repairs.json"


@dataclass(frozen=True)
class ExtractionRepair:
    """A domain-scoped, selector-only repair for body extraction."""

    name: str
    domains: Tuple[str, ...]
    content_selector: str = ""
    remove_selectors: Tuple[str, ...] = ()
    max_length: int = MAX_OUTPUT_CHARS
    source: str = "user"

    @classmethod
    def from_dict(cls, data: Any, source: str = "user") -> Optional["ExtractionRepair"]:
        """Build a repair, or None when anything about it is unsafe.

        Failing closed matters more than salvaging a partial rule: a repair
        that half-applies would silently change what gets indexed.
        """
        if not isinstance(data, dict):
            return None
        domains = tuple(
            _safe_domain(item) for item in data.get("domains", []) if _safe_domain(item)
        )
        if not domains:
            return None

        content_selector = _safe_selector(data.get("content_selector"))
        if data.get("content_selector") and not content_selector:
            return None

        raw_removes = data.get("remove_selectors", [])
        if not isinstance(raw_removes, (list, tuple)):
            return None
        removes: List[str] = []
        for candidate in list(raw_removes)[:MAX_REMOVE_SELECTORS]:
            safe = _safe_selector(candidate)
            if not safe:
                return None
            removes.append(safe)

        if not content_selector and not removes:
            return None

        return cls(
            name=_clean_value(data.get("name"), 100) or "Extraction repair",
            domains=domains,
            content_selector=content_selector,
            remove_selectors=tuple(removes),
            max_length=_clamp_int(data.get("max_length"), 200, MAX_OUTPUT_CHARS, MAX_OUTPUT_CHARS),
            source=source,
        )

    def matches(self, url: str) -> bool:
        domain = _url_domain(url)
        if not domain:
            return False
        return any(domain == d or domain.endswith("." + d) for d in self.domains)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "domains": list(self.domains),
            "content_selector": self.content_selector,
            "remove_selectors": list(self.remove_selectors),
            "max_length": self.max_length,
        }


@dataclass
class RepairResult:
    """What a repair did, for preview and for the caller's decision."""

    applied: bool = False
    rule_name: str = ""
    text: str = ""
    default_text: str = ""
    reason: str = ""

    @property
    def changed(self) -> bool:
        return self.applied and self.text.strip() != self.default_text.strip()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "applied": self.applied,
            "rule": self.rule_name,
            "reason": self.reason,
            "default_chars": len(self.default_text),
            "repaired_chars": len(self.text),
            "changed": self.changed,
        }


def load_extraction_repairs(path: str | Path | None = None) -> List[ExtractionRepair]:
    """Load user repairs. A malformed document yields no repairs, never raises."""
    source = Path(path) if path else REPAIRS_FILE
    if not source.is_file():
        return []
    try:
        payload = _read_template_payload(source)
    except Exception as exc:
        log.warning(f"Could not read extraction repairs from {source.name}: {exc}")
        return []
    items = payload.get("repairs") if isinstance(payload, dict) else payload
    if not isinstance(items, (list, tuple)):
        return []
    repairs: List[ExtractionRepair] = []
    for item in list(items)[:MAX_REPAIRS]:
        rule = ExtractionRepair.from_dict(item, source=str(source.name))
        if rule is not None:
            repairs.append(rule)
    return repairs


def save_extraction_repairs(repairs: List[ExtractionRepair], path: str | Path | None = None) -> Path:
    """Persist repairs, re-validating every one before writing."""
    from bookmark_organizer_pro.utils.runtime import atomic_json_write

    destination = Path(path) if path else REPAIRS_FILE
    payload = {"version": 1, "repairs": []}
    for repair in repairs[:MAX_REPAIRS]:
        checked = ExtractionRepair.from_dict(repair.to_dict(), source=repair.source)
        if checked is None:
            raise ValueError(f"Refusing to save an invalid extraction repair: {repair.name}")
        payload["repairs"].append(checked.to_dict())
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_json_write(destination, payload)
    return destination


def _text_from_soup(node, max_length: int) -> str:
    text = node.get_text(separator="\n", strip=True)
    return _collapse(text)[:max_length]


def _collapse(text: str) -> str:
    lines = [line.strip() for line in str(text or "").splitlines()]
    return "\n".join(line for line in lines if line)


def repair_extraction(
    url: str,
    html: str,
    default_text: str = "",
    repairs: Optional[List[ExtractionRepair]] = None,
) -> RepairResult:
    """Apply the first matching repair to already-fetched HTML.

    Never fetches anything and never evaluates page script: it re-parses the
    same bytes the extractor already had.
    """
    result = RepairResult(default_text=str(default_text or ""), text=str(default_text or ""))
    rules = repairs if repairs is not None else load_extraction_repairs()
    if not rules or not html:
        return result
    if len(html) > MAX_INPUT_CHARS:
        result.reason = "page too large to repair"
        return result

    matching = next((rule for rule in rules if rule.matches(url)), None)
    if matching is None:
        return result

    bs4 = _try_import("bs4")
    if bs4 is None:
        result.reason = "BeautifulSoup is required for extraction repairs"
        return result

    started = time.monotonic()
    try:
        soup = bs4.BeautifulSoup(html, "html.parser")
        for selector in matching.remove_selectors:
            if time.monotonic() - started > REPAIR_TIME_BUDGET_SECONDS:
                result.reason = "repair exceeded its time budget"
                return result
            for node in soup.select(selector):
                node.decompose()

        if matching.content_selector:
            nodes = soup.select(matching.content_selector)
            if not nodes:
                result.reason = "content selector matched nothing"
                return result
            repaired = _collapse("\n".join(
                _text_from_soup(node, matching.max_length) for node in nodes
            ))[: matching.max_length]
        else:
            repaired = _text_from_soup(soup, matching.max_length)
    except Exception as exc:  # a bad selector must not break ingestion
        log.warning(f"Extraction repair {matching.name!r} failed: {exc}")
        result.reason = "repair raised an error"
        return result

    if len(repaired.strip()) < MIN_REPAIRED_CHARS:
        result.reason = "repaired output was too short to trust"
        return result

    result.applied = True
    result.rule_name = matching.name
    result.text = repaired
    result.reason = "repaired"
    return result


def preview_repair(url: str, html: str, repair: ExtractionRepair, default_text: str = "") -> RepairResult:
    """Run one candidate repair without saving it, for side-by-side review."""
    return repair_extraction(url, html, default_text, repairs=[repair])
