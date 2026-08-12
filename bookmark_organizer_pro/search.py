"""Search engine with advanced query parsing and fuzzy matching."""

import re as stdlib_re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import regex as safe_regex

from .models import Bookmark


MAX_REGEX_PATTERN_LENGTH = 250
MAX_REGEX_SEARCH_TEXT = 20_000
REGEX_MATCH_TIMEOUT_SECONDS = 0.02
REGEX_QUERY_BUDGET_SECONDS = 0.5
SAVED_SEARCH_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class SearchDiagnostic:
    """A parser or evaluator error with an exact source span."""

    code: str
    message: str
    start: int
    end: int

    @property
    def display(self) -> str:
        return f"Column {self.start + 1}: {self.message}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "start": self.start,
            "end": self.end,
            "column": self.start + 1,
        }


@dataclass(frozen=True)
class SearchClause:
    """One normalized search predicate."""

    kind: str
    value: Any
    start: int
    end: int
    operator: str = ""
    negated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        value = self.value
        if isinstance(value, datetime):
            value = value.isoformat()
        return {
            "kind": self.kind,
            "value": value,
            "operator": self.operator,
            "negated": self.negated,
            "start": self.start,
            "end": self.end,
        }


@dataclass(frozen=True)
class SearchAST:
    """An OR-of-AND-groups query tree."""

    groups: Tuple[Tuple[SearchClause, ...], ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "or",
            "groups": [
                {
                    "type": "and",
                    "clauses": [clause.to_dict() for clause in group],
                }
                for group in self.groups
            ],
        }


@dataclass(frozen=True)
class _SearchToken:
    value: str
    start: int
    end: int
    quoted: bool = False


def migrate_legacy_search_query(query: str) -> str:
    """Convert the former whole-query /pattern/ syntax to explicit regex: syntax."""
    value = str(query or "")
    stripped = value.strip()
    if len(stripped) >= 2 and stripped.startswith("/") and stripped.endswith("/"):
        pattern = stripped[1:-1]
        escaped = pattern.replace("\\", "\\\\").replace('"', '\\"')
        return f'regex:"{escaped}"'
    return value


class SearchQuery:
    """Parses and represents advanced search queries.

    Grammar::

        query    := and_expr ("OR" and_expr)*
        and_expr := clause (("AND")? clause)*
        clause   := ["-"] (term | field ":" value)

    Adjacent clauses imply AND. OR has lower precedence. Quoted values may
    contain spaces. Invalid input produces positional diagnostics and never
    evaluates as a broader query.
    """

    def __init__(self, raw_query: str = ""):
        self.raw_query = str(raw_query or "")
        self.diagnostics: List[SearchDiagnostic] = []
        self.ast = SearchAST(())
        self.text_terms: List[str] = []
        self.or_terms: List[str] = []
        self.excluded_terms: List[str] = []
        self.domain_filters: List[str] = []
        self.tag_filters: List[str] = []
        self.category_filters: List[str] = []
        self.title_filters: List[str] = []
        self.url_filters: List[str] = []
        self.date_after: Optional[datetime] = None
        self.date_before: Optional[datetime] = None
        self.has_notes: Optional[bool] = None
        self.has_tags: Optional[bool] = None
        self.is_pinned: Optional[bool] = None
        self.is_archived: Optional[bool] = None
        self.is_broken: Optional[bool] = None
        self.is_stale: Optional[bool] = None
        self.min_visits: Optional[int] = None
        self.content_filters: List[str] = []
        self.is_regex: bool = False
        self.regex_pattern: Optional[Any] = None
        self._regex_patterns: Dict[Tuple[int, int], Any] = {}
        self._evaluation_deadline: Optional[float] = None
        self._runtime_error_codes: set[str] = set()

        if self.raw_query:
            self._parse(self.raw_query)

    @property
    def valid(self) -> bool:
        return not self.diagnostics

    @staticmethod
    def _safe_compile_regex(pattern: str) -> Any:
        try:
            return safe_regex.compile(pattern, safe_regex.IGNORECASE)
        except (safe_regex.error, ValueError, OverflowError):
            return None

    def _diagnose(self, code: str, message: str, start: int, end: int) -> None:
        self.diagnostics.append(
            SearchDiagnostic(code, message, max(0, start), max(start + 1, end))
        )

    def _tokenize(self, query: str) -> List[_SearchToken]:
        tokens: List[_SearchToken] = []
        chars: List[str] = []
        token_start: Optional[int] = None
        quote_start: Optional[int] = None
        token_was_quoted = False
        index = 0

        while index < len(query):
            char = query[index]
            if token_start is None and char.isspace():
                index += 1
                continue
            if token_start is None:
                token_start = index

            if char == '"':
                token_was_quoted = True
                if quote_start is None:
                    quote_start = index
                else:
                    quote_start = None
                index += 1
                continue

            if (
                quote_start is not None
                and char == "\\"
                and index + 1 < len(query)
                and query[index + 1] in {'"', "\\"}
            ):
                chars.append(query[index + 1])
                index += 2
                continue

            if char.isspace() and quote_start is None:
                tokens.append(
                    _SearchToken(
                        "".join(chars),
                        token_start,
                        index,
                        quoted=token_was_quoted,
                    )
                )
                chars = []
                token_start = None
                token_was_quoted = False
            else:
                chars.append(char)
            index += 1

        if token_start is not None:
            tokens.append(
                _SearchToken(
                    "".join(chars),
                    token_start,
                    len(query),
                    quoted=token_was_quoted,
                )
            )
        if quote_start is not None:
            self._diagnose(
                "unclosed_quote",
                "Quoted values must end with a matching quote.",
                quote_start,
                len(query),
            )
        return tokens

    def _parse(self, query: str) -> None:
        stripped = query.strip()
        if len(stripped) >= 2 and stripped.startswith("/") and stripped.endswith("/"):
            start = query.find("/")
            self._diagnose(
                "legacy_regex_syntax",
                "Use the explicit regex: prefix instead of /pattern/.",
                start,
                start + len(stripped),
            )
            return

        tokens = self._tokenize(query)
        groups: List[List[SearchClause]] = [[]]
        expecting_clause = True
        previous_operator = ""

        for token in tokens:
            operator = token.value.upper()
            if not token.quoted and operator in {"AND", "OR"}:
                if expecting_clause:
                    self._diagnose(
                        "unexpected_operator",
                        f"{operator} must follow a search clause.",
                        token.start,
                        token.end,
                    )
                    previous_operator = operator
                    continue
                if operator == "OR":
                    groups.append([])
                expecting_clause = True
                previous_operator = operator
                continue

            clause = self._parse_clause(token)
            if clause is not None:
                groups[-1].append(clause)
                expecting_clause = False
                previous_operator = ""

        if tokens and expecting_clause and previous_operator:
            last = tokens[-1]
            self._diagnose(
                "trailing_operator",
                f"{previous_operator} must be followed by a search clause.",
                last.start,
                last.end,
            )

        if self.diagnostics:
            self.ast = SearchAST(())
            return

        normalized_groups = tuple(tuple(group) for group in groups if group)
        self.ast = SearchAST(normalized_groups)
        self._populate_compatibility_fields()

    def _parse_clause(self, token: _SearchToken) -> Optional[SearchClause]:
        raw = token.value
        negated = raw.startswith("-")
        if negated:
            raw = raw[1:]
        if not raw:
            self._diagnose(
                "empty_negation" if negated else "empty_term",
                (
                    "Negation must be followed by a term or filter."
                    if negated
                    else "Search terms cannot be empty."
                ),
                token.start,
                token.end,
            )
            return None

        if raw.startswith("#"):
            value = raw[1:].strip()
            if not value:
                self._diagnose(
                    "empty_filter", "Tag shorthand requires a value.", token.start, token.end
                )
                return None
            return SearchClause("tag", value, token.start, token.end, negated=negated)

        if ":" not in raw or stdlib_re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", raw):
            return SearchClause("term", raw, token.start, token.end, negated=negated)

        field, value = raw.split(":", 1)
        field_lower = field.lower()
        aliases = {"cat": "category"}
        allowed_fields = {
            "domain", "tag", "category", "title", "url", "content",
            "after", "before", "has", "is", "visits", "regex",
        }
        field_lower = aliases.get(field_lower, field_lower)
        if field_lower not in allowed_fields:
            self._diagnose(
                "unknown_field",
                f"Unknown search field '{field}'.",
                token.start,
                token.start + len(field),
            )
            return None
        if not value.strip():
            self._diagnose(
                "empty_filter",
                f"The {field}: filter requires a value.",
                token.start,
                token.end,
            )
            return None
        value = value.strip()

        if field_lower == "domain":
            value = value.lower().removeprefix("www.")
            if not value or any(char.isspace() for char in value):
                self._diagnose(
                    "invalid_domain",
                    "domain: requires one hostname.",
                    token.start,
                    token.end,
                )
                return None
        elif field_lower in {"after", "before"}:
            try:
                value = self._parse_date(value)
            except (TypeError, ValueError):
                self._diagnose(
                    "invalid_date",
                    f"{field}: requires an ISO date such as 2026-07-29.",
                    token.start,
                    token.end,
                )
                return None
        elif field_lower == "has":
            value = value.lower()
            if value not in {"notes", "tags"}:
                self._diagnose(
                    "invalid_has_filter",
                    "has: supports only notes or tags.",
                    token.start,
                    token.end,
                )
                return None
        elif field_lower == "is":
            value = value.lower()
            if value not in {
                "pinned", "archived", "broken", "stale", "recent", "untagged",
                "in-progress", "finished", "unread",
            }:
                self._diagnose(
                    "invalid_status_filter",
                    "is: supports pinned, archived, broken, stale, recent, untagged, in-progress, finished, or unread.",
                    token.start,
                    token.end,
                )
                return None
        elif field_lower == "visits":
            match = stdlib_re.fullmatch(r"(>=|<=|>|<|=)?(\d+)", value)
            if not match:
                self._diagnose(
                    "invalid_visits_filter",
                    "visits: requires a non-negative integer with =, >, >=, <, or <=.",
                    token.start,
                    token.end,
                )
                return None
            operator = match.group(1) or ">="
            return SearchClause(
                "visits",
                int(match.group(2)),
                token.start,
                token.end,
                operator=operator,
                negated=negated,
            )
        elif field_lower == "regex":
            if len(value) > MAX_REGEX_PATTERN_LENGTH:
                self._diagnose(
                    "regex_too_long",
                    f"regex: patterns are limited to {MAX_REGEX_PATTERN_LENGTH} characters.",
                    token.start,
                    token.end,
                )
                return None
            compiled = self._safe_compile_regex(value)
            if compiled is None:
                self._diagnose(
                    "invalid_regex",
                    "regex: contains an invalid regular expression.",
                    token.start,
                    token.end,
                )
                return None
            self._regex_patterns[(token.start, token.end)] = compiled

        return SearchClause(
            field_lower,
            value,
            token.start,
            token.end,
            negated=negated,
        )

    def _populate_compatibility_fields(self) -> None:
        for group_index, group in enumerate(self.ast.groups):
            for clause in group:
                if clause.kind == "term":
                    if clause.negated:
                        self.excluded_terms.append(str(clause.value))
                    elif group_index:
                        self.or_terms.append(str(clause.value))
                    else:
                        self.text_terms.append(str(clause.value))
                elif clause.negated:
                    continue
                elif clause.kind == "domain":
                    self.domain_filters.append(str(clause.value))
                elif clause.kind == "tag":
                    self.tag_filters.append(str(clause.value))
                elif clause.kind == "category":
                    self.category_filters.append(str(clause.value))
                elif clause.kind == "title":
                    self.title_filters.append(str(clause.value))
                elif clause.kind == "url":
                    self.url_filters.append(str(clause.value))
                elif clause.kind == "content":
                    self.content_filters.append(str(clause.value))
                elif clause.kind == "after":
                    self.date_after = clause.value
                elif clause.kind == "before":
                    self.date_before = clause.value
                elif clause.kind == "has":
                    setattr(self, f"has_{clause.value}", True)
                elif clause.kind == "is" and clause.value in {
                    "pinned", "archived", "broken", "stale", "in-progress", "finished", "unread",
                }:
                    setattr(self, f"is_{clause.value}", True)
                elif clause.kind == "visits" and clause.operator in {">", ">="}:
                    self.min_visits = int(clause.value) + (1 if clause.operator == ">" else 0)
                elif clause.kind == "regex":
                    self.is_regex = True
                    self.regex_pattern = self._regex_patterns.get((clause.start, clause.end))

    @staticmethod
    def _parse_date(value: str) -> datetime:
        """Parse an ISO date and normalize timezone-aware values to naive UTC."""
        if not stdlib_re.fullmatch(
            r"\d{4}-\d{2}-\d{2}(?:[Tt ][0-9:.]+(?:[Zz]|[+-]\d{2}:\d{2})?)?",
            value,
        ):
            raise ValueError("not an ISO date")
        parsed = datetime.fromisoformat(value.replace("z", "+00:00").replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    def begin_evaluation(self) -> None:
        """Reset runtime diagnostics and start the total regex budget."""
        self.diagnostics = [
            diagnostic
            for diagnostic in self.diagnostics
            if not diagnostic.code.startswith("regex_runtime_")
        ]
        self._runtime_error_codes.clear()
        self._evaluation_deadline = time.monotonic() + REGEX_QUERY_BUDGET_SECONDS

    def _runtime_error(self, code: str, message: str, clause: SearchClause) -> None:
        if code in self._runtime_error_codes:
            return
        self._runtime_error_codes.add(code)
        self._diagnose(code, message, clause.start, clause.end)

    @staticmethod
    def _searchable_text(bookmark: Bookmark) -> str:
        return " ".join(
            (
                bookmark.title,
                bookmark.url,
                bookmark.notes,
                bookmark.description,
                bookmark.category,
                bookmark.parent_category,
                " ".join(bookmark.tags),
                " ".join(getattr(bookmark, "ai_tags", [])),
            )
        )

    @staticmethod
    def _bookmark_created_at(bookmark: Bookmark) -> Optional[datetime]:
        try:
            parsed = datetime.fromisoformat(bookmark.created_at.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except (AttributeError, TypeError, ValueError):
            return None

    def _matches_clause(self, clause: SearchClause, bookmark: Bookmark) -> bool:
        value = clause.value
        value_lower = str(value).lower()
        all_tags = list(bookmark.tags) + list(getattr(bookmark, "ai_tags", []))

        if clause.kind == "term":
            matched = value_lower in self._searchable_text(bookmark).lower()
        elif clause.kind == "domain":
            domain = bookmark.domain.lower()
            matched = domain == value_lower or domain.endswith("." + value_lower)
        elif clause.kind == "tag":
            prefix = value_lower + "/"
            matched = any(
                tag.lower() == value_lower or tag.lower().startswith(prefix)
                for tag in all_tags
            )
        elif clause.kind == "category":
            matched = (
                value_lower in bookmark.category.lower()
                or value_lower in bookmark.parent_category.lower()
            )
        elif clause.kind == "title":
            matched = value_lower in bookmark.title.lower()
        elif clause.kind == "url":
            matched = value_lower in bookmark.url.lower()
        elif clause.kind == "content":
            body = "\n".join(
                filter(
                    None,
                    [
                        _load_extracted_text(bookmark.id),
                        _load_youtube_transcript(bookmark.id, bookmark.youtube_transcript_path),
                    ],
                )
            )
            matched = bool(body) and value_lower in body.lower()
        elif clause.kind in {"after", "before"}:
            created = self._bookmark_created_at(bookmark)
            matched = created is not None and (
                created >= value if clause.kind == "after" else created <= value
            )
        elif clause.kind == "has":
            matched = (
                bool(bookmark.notes)
                if value == "notes"
                else bool(all_tags)
            )
        elif clause.kind == "is":
            if value == "pinned":
                matched = bookmark.is_pinned
            elif value == "archived":
                matched = bookmark.is_archived
            elif value == "broken":
                matched = not bookmark.is_valid
            elif value == "stale":
                matched = bookmark.is_stale
            elif value == "untagged":
                matched = not all_tags
            elif value == "in-progress":
                matched = getattr(bookmark, "reader_progress_state", "unread") == "in_progress"
            elif value == "finished":
                matched = getattr(bookmark, "reader_progress_state", "unread") == "finished"
            elif value == "unread":
                matched = getattr(bookmark, "reader_progress_state", "unread") == "unread"
            else:
                created = self._bookmark_created_at(bookmark)
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                matched = created is not None and created >= now - timedelta(days=7)
        elif clause.kind == "visits":
            count = bookmark.visit_count
            matched = {
                ">": count > value,
                ">=": count >= value,
                "=": count == value,
                "<": count < value,
                "<=": count <= value,
            }[clause.operator]
        elif clause.kind == "regex":
            if (
                self._evaluation_deadline is not None
                and time.monotonic() >= self._evaluation_deadline
            ):
                self._runtime_error(
                    "regex_runtime_budget",
                    "Regular-expression search exceeded its total time budget.",
                    clause,
                )
                return False
            compiled = self._regex_patterns[(clause.start, clause.end)]
            searchable = self._searchable_text(bookmark)[:MAX_REGEX_SEARCH_TEXT]
            try:
                matched = bool(
                    compiled.search(searchable, timeout=REGEX_MATCH_TIMEOUT_SECONDS)
                )
            except (TimeoutError, RecursionError, MemoryError):
                self._runtime_error(
                    "regex_runtime_timeout",
                    "Regular-expression evaluation exceeded its time budget.",
                    clause,
                )
                return False
        else:  # pragma: no cover - parser constrains kinds
            matched = False

        return not matched if clause.negated else matched

    def matches(self, bookmark: Bookmark) -> bool:
        """Check if a bookmark matches this query, failing closed on errors."""
        if not self.valid or not self.ast.groups:
            return False
        if self._evaluation_deadline is None:
            self.begin_evaluation()
        matched = any(
            all(self._matches_clause(clause, bookmark) for clause in group)
            for group in self.ast.groups
        )
        return matched and self.valid


class SearchEngine:
    """Full-text search engine for bookmarks with relevance scoring."""

    def __init__(self):
        self._search_history: List[str] = []
        self._saved_searches: Dict[str, str] = {}
        self._max_history = 50
        self.last_diagnostics: List[SearchDiagnostic] = []
        self.last_ast = SearchAST(())

    def search(self, bookmarks: List[Bookmark], query: str,
               fuzzy: bool = False) -> List[Tuple[Bookmark, float]]:
        """Search bookmarks with query. Returns (bookmark, relevance_score) tuples."""
        query = str(query or "")
        self.last_diagnostics = []
        self.last_ast = SearchAST(())
        if not query.strip():
            return []

        parsed = SearchQuery(query)
        self.last_diagnostics = list(parsed.diagnostics)
        self.last_ast = parsed.ast
        if not parsed.valid:
            return []

        self._add_to_history(query)
        parsed.begin_evaluation()

        results = []
        for bm in bookmarks:
            if parsed.matches(bm):
                score = self._calculate_relevance(bm, parsed)
                results.append((bm, score))
            if not parsed.valid:
                self.last_diagnostics = list(parsed.diagnostics)
                return []

        results.sort(key=lambda x: x[1], reverse=True)
        self.last_diagnostics = list(parsed.diagnostics)
        return results

    def _calculate_relevance(self, bookmark: Bookmark, query: SearchQuery) -> float:
        """Calculate relevance score for a bookmark"""
        score = 1.0

        for term in query.text_terms + query.or_terms:
            term_lower = term.lower()
            if term_lower in bookmark.title.lower():
                score += 2.0
            if term_lower in bookmark.url.lower():
                score += 1.0
            if term_lower == bookmark.domain.lower():
                score += 3.0

        if bookmark.is_pinned:
            score += 1.0
        if bookmark.visit_count > 0:
            score += min(0.5, bookmark.visit_count * 0.1)
        if bookmark.age_days < 7:
            score += 0.3
        elif bookmark.age_days < 30:
            score += 0.1

        return score

    def _add_to_history(self, query: str):
        """Add query to search history"""
        query = query.strip()
        if query and query not in self._search_history:
            self._search_history.insert(0, query)
            if len(self._search_history) > self._max_history:
                self._search_history.pop()

    def get_history(self) -> List[str]:
        return self._search_history.copy()

    def clear_history(self):
        self._search_history.clear()

    def save_search(self, name: str, query: str) -> None:
        name = str(name or "").strip()
        query = str(query or "").strip()
        if not name or not query:
            raise ValueError("Saved searches require both a name and a query.")
        parsed = SearchQuery(query)
        if not parsed.valid:
            raise ValueError(parsed.diagnostics[0].display)
        self._saved_searches[name] = query

    def load_saved_searches(self, payload: Any) -> None:
        """Load and migrate legacy saved-search dictionaries."""
        if isinstance(payload, dict) and "searches" in payload:
            searches = payload.get("searches", {})
        else:
            searches = payload
        if not isinstance(searches, dict):
            raise ValueError("Saved searches must be a mapping.")

        loaded: Dict[str, str] = {}
        for raw_name, raw_query in searches.items():
            name = str(raw_name or "").strip()
            query = migrate_legacy_search_query(str(raw_query or "").strip())
            if not name or not query:
                continue
            parsed = SearchQuery(query)
            if parsed.valid:
                loaded[name] = query
        self._saved_searches = loaded

    def export_saved_searches(self) -> Dict[str, Any]:
        """Return the current versioned saved-search payload."""
        return {
            "version": SAVED_SEARCH_SCHEMA_VERSION,
            "searches": self.get_saved_searches(),
        }

    def get_saved_searches(self) -> Dict[str, str]:
        return self._saved_searches.copy()

    def delete_saved_search(self, name: str):
        if name in self._saved_searches:
            del self._saved_searches[name]

    @staticmethod
    def get_syntax_help() -> str:
        return """
Search Syntax:

Basic Search:
  python flask           Search for "python" AND "flask"
  "exact phrase"         Search for exact phrase
  python OR rust         Match either AND group
  -deprecated            Exclude a matching clause

Field Filters:
  title:python           Search title only
  url:docs.example      Search URL only

Domain Filter:
  domain:github.com      Only bookmarks from github.com

Tag Filter:
  tag:python  or  #python   Bookmarks with tag "python"

Category Filter:
  category:Development   Bookmarks in Development category
  cat:AI                 Short form

Date Filters:
  after:2024-01-01       Created after date
  before:2024-06-01      Created before date

Status Filters:
  is:pinned              Pinned bookmarks
  is:in-progress         Reader items currently in progress
  is:finished            Reader items marked finished
  is:unread              Reader items not started
  is:archived            Archived bookmarks
  is:broken              Broken links
  is:stale               Not visited in 90+ days

Content Filters:
  content:keyword        Search extracted page text
  has:notes              Has notes
  has:tags               Has tags
  visits:>5              Visited more than 5 times

Regex Search:
  regex:pattern          Search with a time-bounded regular expression
  regex:"a\\s+b"         Quote patterns that contain spaces

Grammar:
  query := and_expr ("OR" and_expr)*
  and_expr := clause (("AND")? clause)*
  clause := ["-"] (term | field ":" value)

Malformed queries return no results and identify the error column.

Examples:
  domain:github.com python       GitHub Python repos
  #tutorial after:2024-01-01     Recent tutorials
  is:stale cat:Shopping          Stale shopping bookmarks
"""


@lru_cache(maxsize=256)
def _load_extracted_text(bookmark_id: int) -> str:
    """Load extracted page text for a bookmark, cached for search sessions."""
    from .constants import EXTRACTED_DIR
    path = EXTRACTED_DIR / f"{bookmark_id}.txt"
    try:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    return ""


@lru_cache(maxsize=256)
def _load_youtube_transcript(bookmark_id: int, path_value: str = "") -> str:
    """Load one opt-in transcript without allowing paths outside app data."""

    from .constants import APP_DIR, YOUTUBE_TRANSCRIPTS_DIR
    from pathlib import Path

    path = Path(path_value).expanduser() if path_value else None
    if path is None:
        matches = sorted(YOUTUBE_TRANSCRIPTS_DIR.glob(f"{int(bookmark_id)}.*.txt"))
        path = matches[-1] if matches else None
    if path is None:
        return ""
    try:
        resolved = path.resolve()
        if not resolved.is_relative_to(APP_DIR.resolve()):
            return ""
        return resolved.read_text(encoding="utf-8", errors="replace")[:2_000_000]
    except (OSError, ValueError):
        return ""


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings"""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def fuzzy_match(query: str, text: str, threshold: float = 0.6) -> Tuple[bool, float]:
    """Check if query fuzzy matches text. Returns (matches, similarity_score)."""
    query = str(query or "").lower()
    text = str(text or "").lower()
    try:
        threshold = max(0.0, min(1.0, float(threshold)))
    except (TypeError, ValueError):
        threshold = 0.6

    if not query.strip() or not text.strip():
        return False, 0.0

    if query in text:
        return True, 1.0

    query_words = query.split()
    text_words = text.split()

    total_score = 0
    matched_words = 0

    for qword in query_words:
        best_score = 0
        for tword in text_words:
            max_len = max(len(qword), len(tword))
            if max_len == 0:
                continue
            distance = levenshtein_distance(qword, tword)
            similarity = 1 - (distance / max_len)
            best_score = max(best_score, similarity)

        if best_score >= threshold:
            matched_words += 1
            total_score += best_score

    if len(query_words) == 0:
        return False, 0.0

    match_ratio = matched_words / len(query_words)
    avg_score = total_score / len(query_words) if query_words else 0

    return match_ratio >= 0.8, avg_score


class FuzzySearchEngine:
    """Enhanced search engine with fuzzy matching"""

    def __init__(self):
        self._cache: Dict[str, List[Tuple[int, float]]] = {}
        self._search_history: List[str] = []
        self._saved_searches: Dict[str, SearchQuery] = {}
        self.last_diagnostics: List[SearchDiagnostic] = []

    def search(self, bookmarks: List[Bookmark], query: str,
               fuzzy: bool = True, threshold: float = 0.6) -> List[Tuple[Bookmark, float]]:
        """Search bookmarks with optional fuzzy matching."""
        query = str(query or "")
        self.last_diagnostics = []
        if not query.strip():
            return [(bm, 1.0) for bm in bookmarks]

        if query not in self._search_history:
            self._search_history.insert(0, query)
            self._search_history = self._search_history[:50]

        try:
            threshold = max(0.0, min(1.0, float(threshold)))
        except (TypeError, ValueError):
            threshold = 0.6

        parsed = SearchQuery(query)
        self.last_diagnostics = list(parsed.diagnostics)
        if not parsed.valid:
            return []
        is_advanced = (
            len(parsed.ast.groups) > 1
            or any(
                clause.kind != "term" or clause.negated
                for group in parsed.ast.groups
                for clause in group
            )
            or bool(stdlib_re.search(r"(?:^|\s)AND(?:\s|$)", query, stdlib_re.IGNORECASE))
        )
        if is_advanced:
            self.last_diagnostics = list(parsed.diagnostics)
            parsed.begin_evaluation()
            results = []
            for bookmark in bookmarks:
                if parsed.matches(bookmark):
                    results.append((bookmark, 1.0))
                if not parsed.valid:
                    self.last_diagnostics = list(parsed.diagnostics)
                    return []
            return results

        results = []
        query_lower = query.lower()

        for bm in bookmarks:
            searchable = (
                f"{bm.title} {bm.url} {bm.notes} "
                f"{' '.join(bm.tags)} {' '.join(getattr(bm, 'ai_tags', []))}"
            )

            if query_lower in searchable.lower():
                score = 1.0
                if query_lower in bm.title.lower():
                    score += 0.5
                if query_lower in bm.domain.lower():
                    score += 0.3
                results.append((bm, score))
                continue

            if fuzzy:
                matches, score = fuzzy_match(query, searchable, threshold)
                if matches:
                    results.append((bm, score * 0.8))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def get_suggestions(self, partial: str, bookmarks: List[Bookmark], limit: int = 5) -> List[str]:
        """Get search suggestions based on partial input"""
        suggestions = set()
        partial_lower = str(partial or "").lower()
        try:
            limit = max(1, min(50, int(limit)))
        except (TypeError, ValueError):
            limit = 5

        for hist in self._search_history:
            if partial_lower in hist.lower():
                suggestions.add(hist)

        for bm in bookmarks:
            if partial_lower in bm.title.lower():
                words = bm.title.split()
                for word in words:
                    if partial_lower in word.lower():
                        suggestions.add(word)

        for bm in bookmarks:
            for tag in list(bm.tags) + list(getattr(bm, "ai_tags", [])):
                if partial_lower in tag.lower():
                    suggestions.add(f"#{tag}")

        return list(suggestions)[:limit]
