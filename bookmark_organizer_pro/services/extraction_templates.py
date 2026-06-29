"""Safe site-specific structured metadata extraction templates."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from bookmark_organizer_pro import constants as app_constants
from bookmark_organizer_pro.logging_config import log


STRUCTURED_METADATA_KEY = "structured_metadata"
USER_TEMPLATE_FILE = app_constants.DATA_DIR / "extraction_templates.json"
MAX_TEMPLATES = 50
MAX_FIELDS_PER_TEMPLATE = 30
MAX_SELECTOR_LENGTH = 240
MAX_VALUE_LENGTH = 2000
MAX_LIST_ITEMS = 20

_FIELD_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_ATTR_NAME_RE = re.compile(r"^[A-Za-z_:][A-Za-z0-9_:.:-]{0,63}$")
_DOMAIN_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BLOCKED_FIELD_NAMES = {"__proto__", "constructor", "prototype"}
_BLOCKED_SELECTOR_PARTS = (":has(", ":contains(", ":-soup-contains", ":matches(")


BUILTIN_TEMPLATES = [
    {
        "name": "GitHub repository",
        "domains": ["github.com"],
        "content_type": "code",
        "fields": {
            "project_title": {"selector": "meta[property='og:title']", "attribute": "content"},
            "description": {"selector": "meta[name='description']", "attribute": "content"},
            "owner": {"selector": "meta[name='octolytics-dimension-user_login']", "attribute": "content"},
            "language": {"selector": "[itemprop='programmingLanguage']"},
        },
    },
    {
        "name": "Documentation page",
        "domains": ["docs.python.org", "developer.mozilla.org", "learn.microsoft.com"],
        "content_type": "documentation",
        "fields": {
            "heading": {"selector": "h1"},
            "description": {"selector": "meta[name='description']", "attribute": "content"},
            "section": {"selector": "nav[aria-label='Breadcrumb'] li", "multiple": True, "max_items": 6},
        },
    },
    {
        "name": "Research paper",
        "domains": ["arxiv.org", "biorxiv.org", "ssrn.com", "dl.acm.org", "ieeexplore.ieee.org"],
        "content_type": "paper",
        "fields": {
            "paper_title": {"selector": "meta[property='og:title']", "attribute": "content"},
            "description": {"selector": "meta[name='description']", "attribute": "content"},
            "citation_title": {"selector": "meta[name='citation_title']", "attribute": "content"},
            "authors": {"selector": "meta[name='citation_author']", "attribute": "content", "multiple": True},
        },
    },
    {
        "name": "Video page",
        "domains": ["youtube.com", "youtu.be", "vimeo.com"],
        "content_type": "video",
        "fields": {
            "video_title": {"selector": "meta[property='og:title']", "attribute": "content"},
            "description": {"selector": "meta[property='og:description']", "attribute": "content"},
            "channel": {"selector": "meta[name='author']", "attribute": "content"},
        },
    },
    {
        "name": "Store listing",
        "domains": ["amazon.com", "etsy.com", "ebay.com"],
        "content_type": "store",
        "fields": {
            "product_title": {"selector": "meta[property='og:title']", "attribute": "content"},
            "description": {"selector": "meta[property='og:description']", "attribute": "content"},
            "price": {"selector": "meta[property='product:price:amount']", "attribute": "content"},
            "currency": {"selector": "meta[property='product:price:currency']", "attribute": "content"},
        },
    },
]


@dataclass(frozen=True)
class ExtractionField:
    """One safe structured metadata extraction rule."""

    name: str
    selector: str = ""
    attribute: str = ""
    meta: str = ""
    constant: str = ""
    multiple: bool = False
    max_items: int = MAX_LIST_ITEMS
    max_length: int = MAX_VALUE_LENGTH

    @classmethod
    def from_dict(cls, name: str, data: Any) -> Optional["ExtractionField"]:
        if not _is_safe_field_name(name):
            return None
        if not isinstance(data, dict):
            return None

        selector = _safe_selector(data.get("selector"))
        meta = _safe_meta_name(data.get("meta"))
        constant = _clean_value(data.get("constant"), MAX_VALUE_LENGTH) if "constant" in data else ""
        attribute = _safe_attribute(data.get("attribute"))
        if data.get("attribute") and not attribute:
            return None
        if not selector and not meta and constant == "":
            return None

        max_items = _clamp_int(data.get("max_items"), 1, MAX_LIST_ITEMS, MAX_LIST_ITEMS)
        max_length = _clamp_int(data.get("max_length"), 1, MAX_VALUE_LENGTH, MAX_VALUE_LENGTH)
        return cls(
            name=name,
            selector=selector,
            attribute=attribute,
            meta=meta,
            constant=constant,
            multiple=bool(data.get("multiple", False)),
            max_items=max_items,
            max_length=max_length,
        )


@dataclass(frozen=True)
class ExtractionTemplate:
    """A domain-scoped collection of safe extraction fields."""

    name: str
    domains: tuple[str, ...]
    fields: tuple[ExtractionField, ...]
    content_type: str = ""
    source: str = "builtin"

    @classmethod
    def from_dict(cls, data: Any, source: str = "builtin") -> Optional["ExtractionTemplate"]:
        if not isinstance(data, dict):
            return None
        name = _clean_value(data.get("name"), 100) or "Structured metadata"
        domains = tuple(_safe_domain(item) for item in data.get("domains", []) if _safe_domain(item))
        if not domains:
            return None
        raw_fields = data.get("fields", {})
        if not isinstance(raw_fields, dict):
            return None
        fields = []
        for field_name, field_data in list(raw_fields.items())[:MAX_FIELDS_PER_TEMPLATE]:
            field_rule = ExtractionField.from_dict(str(field_name), field_data)
            if field_rule is not None:
                fields.append(field_rule)
        if not fields:
            return None
        return cls(
            name=name,
            domains=domains,
            fields=tuple(fields),
            content_type=_clean_value(data.get("content_type"), 80),
            source=source,
        )

    def matches(self, url: str) -> bool:
        domain = _url_domain(url)
        return any(domain == item or domain.endswith("." + item) for item in self.domains)


@dataclass
class StructuredExtractionResult:
    """Structured metadata extracted from one HTML document."""

    matched: bool = False
    template_name: str = ""
    template_source: str = ""
    content_type: str = ""
    fields: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_bookmark_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "template": self.template_name,
            "source": self.template_source,
            "content_type": self.content_type,
            "fields": dict(self.fields),
            "warnings": list(self.warnings[:10]),
        }


def load_extraction_templates(template_path: str | Path | None = None) -> List[ExtractionTemplate]:
    """Load built-in templates plus optional user JSON/YAML templates."""
    templates = _templates_from_payload({"templates": BUILTIN_TEMPLATES}, source="builtin")
    for path in _candidate_template_paths(template_path):
        try:
            payload = _read_template_payload(path)
            templates.extend(_templates_from_payload(payload, source=str(path)))
        except Exception as exc:
            log.warning(f"Could not load extraction templates from {path}: {exc}")
    return templates[:MAX_TEMPLATES]


def extract_structured_metadata(
    url: str,
    html: str,
    templates: Optional[Iterable[ExtractionTemplate]] = None,
) -> StructuredExtractionResult:
    """Extract structured metadata using the first matching safe template."""
    result = StructuredExtractionResult()
    if not html:
        return result
    template_list = list(templates) if templates is not None else load_extraction_templates()
    template = next((item for item in template_list if item.matches(url)), None)
    if template is None:
        return result

    result.matched = True
    result.template_name = template.name
    result.template_source = template.source
    result.content_type = template.content_type

    bs4 = _try_import("bs4")
    if bs4 is None:
        result.warnings.append("BeautifulSoup is unavailable")
        return result
    try:
        soup = bs4.BeautifulSoup(html, "html.parser")
    except Exception as exc:
        result.warnings.append(f"HTML parse failed: {exc}")
        return result

    for field_rule in template.fields:
        try:
            value = _extract_field(soup, field_rule)
        except Exception as exc:
            result.warnings.append(f"{field_rule.name}: selector failed")
            log.debug(f"structured extraction selector failed for {field_rule.name}: {exc}")
            continue
        if value not in ("", [], None):
            result.fields[field_rule.name] = value
    return result


def structured_metadata_payload(bookmark: Any) -> Dict[str, Any]:
    data = getattr(bookmark, "custom_data", {}) if bookmark is not None else {}
    if not isinstance(data, dict):
        return {}
    payload = data.get(STRUCTURED_METADATA_KEY)
    return payload if isinstance(payload, dict) else {}


def structured_metadata_fields(bookmark: Any) -> Dict[str, Any]:
    payload = structured_metadata_payload(bookmark)
    fields = payload.get("fields")
    return fields if isinstance(fields, dict) else {}


def format_structured_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(_clean_value(item, 200) for item in value if _clean_value(item, 200))
    return _clean_value(value, 500)


def _templates_from_payload(payload: Any, source: str) -> List[ExtractionTemplate]:
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = payload.get("templates", [])
    else:
        raw_items = []
    templates = []
    for item in list(raw_items)[:MAX_TEMPLATES]:
        template = ExtractionTemplate.from_dict(item, source=source)
        if template is not None:
            templates.append(template)
    return templates


def _candidate_template_paths(template_path: str | Path | None) -> List[Path]:
    if template_path:
        return [Path(template_path)]
    return [USER_TEMPLATE_FILE] if USER_TEMPLATE_FILE.exists() else []


def _read_template_payload(path: Path) -> Any:
    text = Path(path).read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        yaml = _try_import("yaml")
        if yaml is None:
            raise ValueError("PyYAML is not installed")
        return yaml.safe_load(text)
    return json.loads(text)


def _extract_field(soup: Any, field_rule: ExtractionField) -> Any:
    if field_rule.constant:
        return field_rule.constant
    if field_rule.meta:
        values = _extract_meta(soup, field_rule)
    else:
        values = _extract_selector(soup, field_rule)
    if field_rule.multiple:
        cleaned = []
        seen = set()
        for item in values[:field_rule.max_items]:
            value = _clean_value(item, field_rule.max_length)
            key = value.lower()
            if value and key not in seen:
                cleaned.append(value)
                seen.add(key)
        return cleaned
    return _clean_value(values[0] if values else "", field_rule.max_length)


def _extract_meta(soup: Any, field_rule: ExtractionField) -> List[str]:
    out = []
    for attrs in ({"name": field_rule.meta}, {"property": field_rule.meta}):
        for tag in soup.find_all("meta", attrs=attrs, limit=field_rule.max_items):
            out.append(str(tag.get("content") or ""))
    return out


def _extract_selector(soup: Any, field_rule: ExtractionField) -> List[str]:
    nodes = soup.select(field_rule.selector, limit=field_rule.max_items)
    out = []
    for node in nodes:
        if field_rule.attribute:
            out.append(str(node.get(field_rule.attribute) or ""))
        else:
            out.append(node.get_text(" ", strip=True))
    return out


def _try_import(name: str):
    try:
        import importlib
        return importlib.import_module(name)
    except Exception:
        return None


def _url_domain(url: str) -> str:
    try:
        return (urlparse(str(url or "")).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _safe_domain(value: Any) -> str:
    domain = str(value or "").strip().lower().removeprefix("www.")
    if not domain or ".." in domain or not _DOMAIN_RE.match(domain):
        return ""
    return domain.strip(".")


def _is_safe_field_name(value: str) -> bool:
    name = str(value or "")
    if name.lower() in _BLOCKED_FIELD_NAMES or name.startswith("_"):
        return False
    return bool(_FIELD_NAME_RE.match(name))


def _safe_selector(value: Any) -> str:
    selector = str(value or "").strip()
    if not selector or len(selector) > MAX_SELECTOR_LENGTH:
        return ""
    lowered = selector.lower()
    if any(part in lowered for part in _BLOCKED_SELECTOR_PARTS):
        return ""
    return selector


def _safe_meta_name(value: Any) -> str:
    meta = str(value or "").strip()
    if not meta or len(meta) > 120:
        return ""
    if not re.match(r"^[A-Za-z0-9_.:-]+$", meta):
        return ""
    return meta


def _safe_attribute(value: Any) -> str:
    attr = str(value or "").strip()
    if not attr:
        return ""
    if attr.lower().startswith("on") or not _ATTR_NAME_RE.match(attr):
        return ""
    return attr


def _clean_value(value: Any, max_length: int) -> str:
    text = str(value or "")
    text = _CONTROL_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max(1, max_length)]


def _clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))
