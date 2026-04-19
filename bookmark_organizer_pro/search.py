"""Search engine with advanced query parsing and fuzzy matching."""

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .models import Bookmark


class SearchQuery:
    """Parses and represents advanced search queries.

    Supports: quoted phrases, field filters (title:, url:, tag:, category:),
    boolean operators, negation, date/status filters, regex mode.
    """

    def __init__(self, raw_query: str = ""):
        self.raw_query = raw_query
        self.text_terms: List[str] = []
        self.or_terms: List[str] = []
        self.excluded_terms: List[str] = []
        self.domain_filters: List[str] = []
        self.tag_filters: List[str] = []
        self.category_filters: List[str] = []
        self.date_after: Optional[datetime] = None
        self.date_before: Optional[datetime] = None
        self.has_notes: Optional[bool] = None
        self.has_tags: Optional[bool] = None
        self.is_pinned: Optional[bool] = None
        self.is_archived: Optional[bool] = None
        self.is_broken: Optional[bool] = None
        self.is_stale: Optional[bool] = None
        self.min_visits: Optional[int] = None
        self.is_regex: bool = False
        self.regex_pattern: Optional[re.Pattern] = None

        if raw_query:
            self._parse(raw_query)

    def _parse(self, query: str):
        """Parse the query string into structured filters"""
        if query.startswith("/") and "/" in query[1:]:
            end_idx = query.rindex("/")
            if end_idx > 0:
                try:
                    pattern = query[1:end_idx]
                    if len(pattern) > 250:
                        return
                    self.regex_pattern = re.compile(pattern, re.IGNORECASE)
                    self.is_regex = True
                    return
                except re.error:
                    pass

        tokens = []
        current_token = ""
        in_quotes = False

        for char in query:
            if char == '"':
                in_quotes = not in_quotes
            elif char == ' ' and not in_quotes:
                if current_token:
                    tokens.append(current_token)
                    current_token = ""
            else:
                current_token += char

        if current_token:
            tokens.append(current_token)

        next_is_or = False
        for token in tokens:
            lower_token = token.lower()

            if lower_token == "and":
                continue
            if lower_token == "or":
                if self.text_terms:
                    self.or_terms.append(self.text_terms.pop())
                next_is_or = True
                continue

            if lower_token.startswith("domain:"):
                self.domain_filters.append(token[7:].lower())
            elif lower_token.startswith("tag:"):
                self.tag_filters.append(token[4:])
            elif token.startswith("#"):
                self.tag_filters.append(token[1:])
            elif lower_token.startswith("category:"):
                self.category_filters.append(token[9:])
            elif lower_token.startswith("cat:"):
                self.category_filters.append(token[4:])
            elif lower_token.startswith("before:"):
                try:
                    self.date_before = self._parse_date(token[7:])
                except Exception:
                    pass
            elif lower_token.startswith("after:"):
                try:
                    self.date_after = self._parse_date(token[6:])
                except Exception:
                    pass
            elif lower_token == "has:notes":
                self.has_notes = True
            elif lower_token == "has:tags":
                self.has_tags = True
            elif lower_token == "is:pinned":
                self.is_pinned = True
            elif lower_token == "is:archived":
                self.is_archived = True
            elif lower_token == "is:broken":
                self.is_broken = True
            elif lower_token == "is:stale":
                self.is_stale = True
            elif lower_token.startswith("visits:"):
                try:
                    val = token[7:]
                    if val.startswith(">"):
                        self.min_visits = int(val[1:])
                    else:
                        self.min_visits = int(val)
                except Exception:
                    pass
            else:
                term = token.strip('"')
                if term.startswith("-") and len(term) > 1:
                    self.excluded_terms.append(term[1:])
                elif next_is_or:
                    self.or_terms.append(term)
                    next_is_or = False
                else:
                    self.text_terms.append(term)

    @staticmethod
    def _parse_date(value: str) -> datetime:
        """Parse a date filter and normalize timezone-aware values."""
        return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=None)

    def matches(self, bookmark: Bookmark) -> bool:
        """Check if a bookmark matches this query"""
        if self.is_regex and self.regex_pattern:
            searchable = (
                f"{bookmark.title} {bookmark.url} {bookmark.notes} "
                f"{' '.join(bookmark.tags)} {' '.join(getattr(bookmark, 'ai_tags', []))}"
            )
            return bool(self.regex_pattern.search(searchable))

        for domain in self.domain_filters:
            bm_domain = bookmark.domain.lower()
            if bm_domain != domain and not bm_domain.endswith("." + domain):
                return False

        for tag in self.tag_filters:
            tag_lower = tag.lower()
            all_tags = list(bookmark.tags) + list(getattr(bookmark, "ai_tags", []))
            if not any(tag_lower == t.lower() for t in all_tags):
                return False

        for cat in self.category_filters:
            cat_lower = cat.lower()
            if cat_lower not in bookmark.category.lower() and \
               cat_lower not in bookmark.parent_category.lower():
                return False

        if self.date_after:
            try:
                created = datetime.fromisoformat(bookmark.created_at.replace('Z', '+00:00'))
                if created.replace(tzinfo=None) < self.date_after:
                    return False
            except Exception:
                pass

        if self.date_before:
            try:
                created = datetime.fromisoformat(bookmark.created_at.replace('Z', '+00:00'))
                if created.replace(tzinfo=None) > self.date_before:
                    return False
            except Exception:
                pass

        if self.has_notes is True and not bookmark.notes:
            return False
        if self.has_tags is True and not (bookmark.tags or getattr(bookmark, "ai_tags", [])):
            return False
        if self.is_pinned is True and not bookmark.is_pinned:
            return False
        if self.is_archived is True and not bookmark.is_archived:
            return False
        if self.is_broken is True and bookmark.is_valid:
            return False
        if self.is_stale is True and not bookmark.is_stale:
            return False

        if self.min_visits is not None and bookmark.visit_count < self.min_visits:
            return False

        searchable = f"{bookmark.title} {bookmark.url} {bookmark.notes} {bookmark.description}".lower()

        for term in self.excluded_terms:
            if term.lower() in searchable:
                return False

        if self.or_terms and not any(term.lower() in searchable for term in self.or_terms):
            return False

        for term in self.text_terms:
            if term.lower() not in searchable:
                return False

        return True


class SearchEngine:
    """Full-text search engine for bookmarks with relevance scoring."""

    def __init__(self):
        self._search_history: List[str] = []
        self._saved_searches: Dict[str, str] = {}
        self._max_history = 50

    def search(self, bookmarks: List[Bookmark], query: str,
               fuzzy: bool = False) -> List[Tuple[Bookmark, float]]:
        """Search bookmarks with query. Returns (bookmark, relevance_score) tuples."""
        query = str(query or "")
        if not query.strip():
            return [(bm, 1.0) for bm in bookmarks]

        self._add_to_history(query)
        parsed = SearchQuery(query)

        results = []
        for bm in bookmarks:
            if parsed.matches(bm):
                score = self._calculate_relevance(bm, parsed)
                results.append((bm, score))

        results.sort(key=lambda x: x[1], reverse=True)
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

    def save_search(self, name: str, query: str):
        self._saved_searches[name] = query

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
  is:archived            Archived bookmarks
  is:broken              Broken links
  is:stale               Not visited in 90+ days

Content Filters:
  has:notes              Has notes
  has:tags               Has tags
  visits:>5              Visited more than 5 times

Regex Search:
  /pattern/              Search with regex

Examples:
  domain:github.com python       GitHub Python repos
  #tutorial after:2024-01-01     Recent tutorials
  is:stale cat:Shopping          Stale shopping bookmarks
"""


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
    query = query.lower()
    text = text.lower()

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

    def search(self, bookmarks: List[Bookmark], query: str,
               fuzzy: bool = True, threshold: float = 0.6) -> List[Tuple[Bookmark, float]]:
        """Search bookmarks with optional fuzzy matching."""
        query = str(query or "")
        if not query.strip():
            return [(bm, 1.0) for bm in bookmarks]

        if query not in self._search_history:
            self._search_history.insert(0, query)
            self._search_history = self._search_history[:50]

        if any(x in query for x in [':', '#', '/', 'is:', 'has:']):
            parsed = SearchQuery(query)
            return [(bm, 1.0) for bm in bookmarks if parsed.matches(bm)]

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
        partial_lower = partial.lower()

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
