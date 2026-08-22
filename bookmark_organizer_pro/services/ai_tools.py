"""AI-related background services and usage helpers."""

from __future__ import annotations

import re
import json
import threading
import urllib.parse
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Callable

from bookmark_organizer_pro.ai import AIClient, AIConfigManager, create_ai_client
from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.search import levenshtein_distance
from bookmark_organizer_pro.utils import safe_float
from bookmark_organizer_pro.utils.safe import sanitize_for_prompt
from bookmark_organizer_pro.utils.runtime import atomic_json_write as _atomic_json_write
from bookmark_organizer_pro.services.ai_audit_log import log_batch_result
from bookmark_organizer_pro.services.tag_linter import _slug as normalize_tag
from bookmark_organizer_pro.services.ai_operation import (
    AIBudget,
    AIBudgetExceeded,
    AICancellationToken,
    AIOperation,
    AIOperationCancelled,
    call_ai,
    operation_scope,
)


class AIBatchProcessor:
    """Background AI processing queue for bookmarks"""
    
    def __init__(self, ai_config: AIConfigManager, 
                 on_progress: Callable = None,
                 on_complete: Callable = None):
        self.ai_config = ai_config
        self.on_progress = on_progress
        self.on_complete = on_complete
        
        self._queue: List[Bookmark] = []
        self._processed: int = 0
        self._running = False
        self._client: Optional[AIClient] = None
        self._thread: Optional[threading.Thread] = None
        self._results: Dict[int, Dict] = {}  # bookmark_id -> result
        self._errors: List[Tuple[int, str]] = []  # (bookmark_id, error_message)
        self._lock = threading.RLock()
        self.cancel_token = AICancellationToken()
        self._operation: Optional[AIOperation] = None
    
    def add_to_queue(self, bookmarks: List[Bookmark]):
        """Add bookmarks to processing queue"""
        with self._lock:
            for bookmark in bookmarks or []:
                if isinstance(bookmark, Bookmark):
                    self._queue.append(bookmark)
    
    def clear_queue(self):
        """Clear the queue"""
        with self._lock:
            self._queue.clear()
    
    def start(self):
        """Start processing in background thread"""
        with self._lock:
            if self._running or not self._queue:
                return
            self._running = True
            self._processed = 0
            self._results.clear()
            self._errors.clear()
            self.cancel_token = AICancellationToken()
            self._operation = AIOperation("batch_processor", token=self.cancel_token)
        
        # Create AI client
        try:
            self._client = create_ai_client(self.ai_config)
        except Exception as e:
            self._running = False
            if self._operation is not None:
                self._operation.fail(e, retryable=False)
            if self.on_complete:
                try:
                    self.on_complete(False, str(e))
                except Exception as callback_exc:
                    log.warning(f"AI batch completion callback failed: {callback_exc}")
            return
        
        # Start worker thread
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop processing"""
        self.cancel_token.cancel()
        self._running = False
    
    def _worker(self):
        """Worker thread for processing bookmarks"""
        operation = self._operation
        try:
            with operation if operation is not None else operation_scope("batch_processor") as active_operation:
                batch_size = self.ai_config.get_batch_size()
                rate_limit_delay = max(0.1, 60.0 / max(1, self.ai_config.get_rate_limit()))

                with self._lock:
                    total = len(self._queue)

                while self._running:
                    active_operation.check()
                    # Process in batches
                    with self._lock:
                        if not self._queue:
                            break
                        batch = self._queue[:batch_size]
                        del self._queue[:batch_size]

                    for bookmark in batch:
                        active_operation.check()
                        if not self._running:
                            raise AIOperationCancelled()

                        try:
                            old_category = bookmark.category
                            old_tags = list(bookmark.tags)
                            old_title = bookmark.title

                            # Get AI categorization and tags
                            result = self._process_bookmark(bookmark, active_operation)
                            active_operation.check()
                            with self._lock:
                                self._results[bookmark.id] = result

                            applied = False
                            # Apply results
                            if result.get("category"):
                                bookmark.category = result["category"]
                                bookmark.ai_categorized = True
                                bookmark.ai_confidence = result.get("confidence", 0.0)
                                applied = True

                            if result.get("tags"):
                                existing = {str(tag).lower() for tag in bookmark.tags}
                                for tag in result["tags"]:
                                    tag_text = str(tag or "").strip()
                                    if tag_text and tag_text.lower() not in existing:
                                        bookmark.tags.append(tag_text)
                                        existing.add(tag_text.lower())
                                applied = True

                            if result.get("summary"):
                                if not bookmark.notes:
                                    bookmark.notes = result["summary"]
                                    applied = True

                            # Audit log
                            try:
                                provider = self.ai_config.get_provider()
                                model = self.ai_config.get_model()
                                log_batch_result(
                                    provider=provider, model=model,
                                    bookmark_id=bookmark.id, url=bookmark.url,
                                    old_category=old_category, old_tags=old_tags,
                                    old_title=old_title, result=result,
                                    applied=applied,
                                )
                            except Exception:
                                pass

                        except (AIOperationCancelled, AIBudgetExceeded):
                            raise
                        except Exception as e:
                            with self._lock:
                                self._errors.append((bookmark.id, str(e)))

                        with self._lock:
                            self._processed += 1
                            processed = self._processed

                        if self.on_progress:
                            try:
                                self.on_progress(processed, total, bookmark)
                            except Exception as callback_exc:
                                log.warning(f"AI batch progress callback failed: {callback_exc}")

                        if rate_limit_delay:
                            active_operation.wait(rate_limit_delay)

                active_operation.check()
                self._running = False
                if self.on_complete:
                    with self._lock:
                        processed = self._processed
                    self.on_complete(True, f"Processed {processed} bookmarks")
        except AIOperationCancelled:
            self._running = False
            if self.on_complete:
                self.on_complete(False, "Cancelled; no partial AI result was cached")
        except AIBudgetExceeded as exc:
            self._running = False
            if self.on_complete:
                self.on_complete(False, str(exc))
        except Exception as exc:
            self._running = False
            if operation is not None and operation.status == "running":
                operation.fail(exc)
            if self.on_complete:
                self.on_complete(False, str(exc))

    def _process_bookmark(self, bookmark: Bookmark, operation: AIOperation | None = None) -> Dict:
        """Process a single bookmark with AI"""
        result = {}
        
        # Build prompt for categorization + tags + summary
        prompt = f"""Analyze this bookmark and provide:
1. Best category from common bookmark categories
2. 3-5 DESCRIPTIVE tags about the content topic (lowercase, hyphens ok)
   - Tags must describe WHAT the content is about, NOT the website name
   - NEVER use the domain name as a tag (no "reddit", "youtube", "github", "amazon")
   - NEVER use generic words like "blog", "website", "page", "online"
   - Good examples: "python-tutorial", "home-repair", "stock-trading", "cybersecurity"
3. A brief 1-sentence summary

URL: {sanitize_for_prompt(bookmark.url, 500)}
Title: {sanitize_for_prompt(bookmark.title, 200)}
Current Category: {sanitize_for_prompt(bookmark.category, 100)}
Domain: {sanitize_for_prompt(bookmark.domain, 100)}

Respond in JSON format:
{{"category": "...", "tags": ["...", "..."], "summary": "...", "confidence": 0.0-1.0}}"""
        
        try:
            response_text = call_ai(
                self._client.complete,
                prompt,
                system="You are a bookmark analysis assistant. Respond only with valid JSON.",
                max_tokens=400,
                temperature=0.3,
                operation=operation,
            )

            if response_text:
                import re as _re
                json_match = _re.search(r'\{[\s\S]*\}', response_text)
                if json_match:
                    import json as _json
                    parsed = _json.loads(json_match.group())
                    category = str(parsed.get("category") or bookmark.category).strip()
                    result["category"] = category or bookmark.category
                    result["confidence"] = max(0.0, min(1.0, safe_float(parsed.get("confidence", 0.5), 0.5)))
                    tags = parsed.get("tags", [])
                    if isinstance(tags, str):
                        tags = tags.split(",")
                    result["tags"] = [
                        str(tag).strip()
                        for tag in (tags or [])
                        if str(tag).strip()
                    ][:10]
                    result["summary"] = str(parsed.get("summary") or "")[:1000]
        except (AIOperationCancelled, AIBudgetExceeded):
            raise
        except Exception as e:
            log.warning(f"AI processing failed for {bookmark.url}: {e}")
        
        return result
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def progress(self) -> Tuple[int, int]:
        with self._lock:
            return self._processed, len(self._queue) + self._processed
    
    @property
    def results(self) -> Dict[int, Dict]:
        with self._lock:
            return self._results.copy()
    
    @property
    def errors(self) -> List[Tuple[int, str]]:
        with self._lock:
            return self._errors.copy()


class AITagSuggester:
    """Generate tag suggestions using AI"""

    _MAX_CACHE = 2048

    # Pages that never carry useful topical tags. Tagging them is how a library
    # fills up with "403", "cloudflare", and "accept-cookies" tags.
    _UNTAGGABLE_PATTERNS = (
        (re.compile(r"\b(?:40[13489]|429|50[023])\b(?!\s*[-\w])"), "http-error-page"),
        (re.compile(r"\berror\s+(?:40[13489]|429|50[023])\b"), "http-error-page"),
        (re.compile(r"\b(?:page\s+not\s+found|not\s+found|forbidden|access\s+denied)\b"), "http-error-page"),
        (re.compile(r"\b(?:sign\s*in|log\s*in|login|sign\s*up)\b.*\b(?:to\s+continue|required)\b"), "login-wall"),
        (re.compile(r"\b(?:please\s+(?:sign|log)\s*in|authentication\s+required)\b"), "login-wall"),
        (re.compile(r"\b(?:captcha|recaptcha|hcaptcha)\b"), "captcha"),
        (re.compile(r"\b(?:are\s+you\s+(?:a\s+)?(?:human|robot)|verify\s+you\s+are\s+(?:a\s+)?human)\b"), "captcha"),
        (re.compile(r"\b(?:just\s+a\s+moment|checking\s+your\s+browser|enable\s+javascript\s+and\s+cookies)\b"), "captcha"),
        (re.compile(r"\b(?:accept\s+(?:all\s+)?cookies|cookie\s+(?:policy|consent|preferences)|we\s+use\s+cookies)\b"), "cookie-wall"),
    )

    def __init__(self, ai_config: AIConfigManager):
        self.ai_config = ai_config
        self._cache: Dict[str, List[str]] = {}

    @classmethod
    def untaggable_reason(cls, *texts: Optional[str]) -> Optional[str]:
        """Return why a page cannot carry topical tags, or None when it can."""
        haystack = " ".join(str(t) for t in texts if t).lower()
        if not haystack.strip():
            return None
        for pattern, reason in cls._UNTAGGABLE_PATTERNS:
            if pattern.search(haystack):
                return reason
        return None

    def _vocabulary(self, existing_tags: Optional[List[str]]) -> List[str]:
        seen: Dict[str, None] = {}
        for tag in existing_tags or []:
            slug = normalize_tag(str(tag))
            if slug:
                seen.setdefault(slug, None)
        return list(seen)

    def _build_prompt(self, bookmark: Bookmark, vocabulary: List[str], mode: str, limit: int) -> str:
        # A capped, vocabulary-anchored prompt. Asking for tags that must NOT
        # duplicate existing ones guarantees a new tag on every bookmark.
        shown = vocabulary[:200]
        if mode == "existing-only" and shown:
            instruction = (
                f"Choose at most {limit} tags for this bookmark, using ONLY tags from the "
                f"allowed list. Never invent a tag. Return an empty array if none apply."
            )
        elif mode == "existing-only":
            instruction = "Return an empty array: no tags exist yet and new tags are not allowed."
        elif mode == "prefer-existing" and shown:
            instruction = (
                f"Choose at most {limit} tags for this bookmark. Strongly prefer reusing tags "
                f"from the existing list; only invent a tag when nothing existing fits."
            )
        else:
            instruction = f"Suggest at most {limit} tags for this bookmark."
        vocabulary_block = (
            "Existing tags: " + json.dumps(shown) if shown else "Existing tags: none yet"
        )
        return f"""{instruction}
Tags must be lowercase, one or two words, and describe the content, topic, or purpose.

{vocabulary_block}

URL: {sanitize_for_prompt(bookmark.url, 500)}
Title: {sanitize_for_prompt(bookmark.title, 200)}
Domain: {sanitize_for_prompt(bookmark.domain, 100)}
Notes: {sanitize_for_prompt(bookmark.notes[:200] if bookmark.notes else 'None', 200)}

Return only a JSON array of tag strings: ["tag1", "tag2", ...]"""

    def _finalize(self, tags: List[str], vocabulary: List[str], mode: str, limit: int) -> List[str]:
        allowed = set(vocabulary)
        result: List[str] = []
        for raw in tags:
            slug = normalize_tag(str(raw))
            if not slug or slug in result:
                continue
            if mode == "existing-only" and slug not in allowed:
                continue
            result.append(slug)
            if len(result) >= limit:
                break
        return result

    def suggest_tags(
        self,
        bookmark: Bookmark,
        existing_tags: List[str] = None,
        *,
        page_text: Optional[str] = None,
        operation: AIOperation | None = None,
        cancel_token: AICancellationToken | None = None,
        budget: AIBudget | None = None,
        job_ledger=None,
    ) -> List[str]:
        """Get AI-suggested tags for a bookmark"""
        provider = getattr(self.ai_config, "get_provider", lambda: "")
        backend = provider() if callable(provider) else ""
        mode = self.ai_config.get_tag_vocabulary_mode()
        limit = self.ai_config.get_max_suggested_tags()
        vocabulary = self._vocabulary(existing_tags)
        with operation_scope(
            "tag_suggestion",
            operation=operation,
            token=cancel_token,
            budget=budget,
            job_ledger=job_ledger,
            backend=str(backend or ""),
            bookmark_id=getattr(bookmark, "id", None),
            url_or_domain=getattr(bookmark, "domain", ""),
        ) as owned_operation:
            owned_operation.check()

            suppressed = self.untaggable_reason(bookmark.title, page_text)
            if suppressed:
                owned_operation.fail(f"tagging skipped: {suppressed}", retryable=False)
                log.info(f"Skipped tag suggestion for {bookmark.url}: {suppressed}")
                return []

            cache_key = f"{mode}:{limit}:{bookmark.url}:{bookmark.title}"
            if cache_key in self._cache:
                return self._cache[cache_key]

            try:
                client = create_ai_client(self.ai_config)
                prompt = self._build_prompt(bookmark, vocabulary, mode, limit)
                response_text = call_ai(
                    client.complete,
                    prompt,
                    system="You are a tag suggestion assistant. Respond only with a JSON array of strings.",
                    max_tokens=200,
                    temperature=0.3,
                    operation=owned_operation,
                )
                owned_operation.check()
                if response_text:
                    arr_match = re.search(r'\[[\s\S]*?\]', response_text)
                    if arr_match:
                        tags = json.loads(arr_match.group())
                        if isinstance(tags, list):
                            cleaned = self._finalize(tags, vocabulary, mode, limit)
                            if len(self._cache) >= self._MAX_CACHE:
                                try:
                                    self._cache.pop(next(iter(self._cache)))
                                except StopIteration:
                                    pass
                            self._cache[cache_key] = cleaned
                            return cleaned
            except (AIOperationCancelled, AIBudgetExceeded):
                raise
            except Exception as e:
                owned_operation.fail(e)
                log.warning(f"AI tag suggestion failed for {bookmark.url}: {e}")

            # Fallback: generate from content
            return self._finalize(
                self._generate_fallback_tags(bookmark), vocabulary, mode, limit
            )
    
    def _generate_fallback_tags(self, bookmark: Bookmark) -> List[str]:
        """Generate tags without AI"""
        tags = set()
        
        # From domain
        domain_parts = bookmark.domain.replace('.', ' ').split()
        for part in domain_parts:
            if len(part) > 3 and part not in ['www', 'com', 'org', 'net', 'edu']:
                tags.add(part.lower())
        
        # From title words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        words = re.findall(r'\b[a-zA-Z]{4,}\b', bookmark.title.lower())
        for word in words[:5]:
            if word not in stop_words:
                tags.add(word)
        
        return list(tags)[:7]


class SemanticDuplicateDetector:
    """Detect semantically similar bookmarks using AI"""
    
    def __init__(self, ai_config: AIConfigManager):
        self.ai_config = ai_config
    
    def find_similar(self, bookmarks: List[Bookmark], 
                     threshold: float = 0.7) -> List[List[Bookmark]]:
        """
        Find groups of semantically similar bookmarks.
        Returns list of groups (each group is a list of similar bookmarks).
        """
        bookmarks = [bm for bm in (bookmarks or []) if bm is not None]
        try:
            threshold = max(0.0, min(1.0, float(threshold)))
        except (TypeError, ValueError):
            threshold = 0.7

        if len(bookmarks) < 2:
            return []
        
        # Group by domain first (optimization)
        by_domain: Dict[str, List[Bookmark]] = {}
        for bm in bookmarks:
            domain = str(getattr(bm, "domain", "") or "")
            if domain not in by_domain:
                by_domain[domain] = []
            by_domain[domain].append(bm)
        
        similar_groups = []
        
        # Check within same domain
        for domain, domain_bms in by_domain.items():
            if len(domain_bms) < 2:
                continue
            
            groups = self._find_similar_in_group(domain_bms, threshold)
            similar_groups.extend(groups)
        
        # Check across different domains with similar titles
        cross_domain = self._find_cross_domain_similar(bookmarks, threshold)
        similar_groups.extend(cross_domain)
        
        return similar_groups
    
    def _find_similar_in_group(self, bookmarks: List[Bookmark], 
                                threshold: float) -> List[List[Bookmark]]:
        """Find similar bookmarks within a group"""
        groups = []
        used = set()
        
        for i, bm1 in enumerate(bookmarks):
            if bm1.id in used:
                continue
            
            group = [bm1]
            
            for bm2 in bookmarks[i+1:]:
                if bm2.id in used:
                    continue
                
                similarity = self._calculate_similarity(bm1, bm2)
                if similarity >= threshold:
                    group.append(bm2)
                    used.add(bm2.id)
            
            if len(group) > 1:
                groups.append(group)
                used.add(bm1.id)
        
        return groups
    
    def _find_cross_domain_similar(self, bookmarks: List[Bookmark],
                                    threshold: float) -> List[List[Bookmark]]:
        """Find similar bookmarks across domains"""
        groups = []
        
        # Use title similarity for cross-domain
        for i, bm1 in enumerate(bookmarks):
            similar = []
            
            for bm2 in bookmarks[i+1:]:
                if str(getattr(bm1, "domain", "") or "") == str(getattr(bm2, "domain", "") or ""):
                    continue
                
                # Title similarity
                title_sim = self._title_similarity(getattr(bm1, "title", ""), getattr(bm2, "title", ""))
                if title_sim >= threshold:
                    similar.append(bm2)
            
            if similar:
                groups.append([bm1] + similar)
        
        return groups
    
    def _calculate_similarity(self, bm1: Bookmark, bm2: Bookmark) -> float:
        """Calculate similarity score between two bookmarks"""
        scores = []
        
        # URL path similarity
        try:
            path1 = urllib.parse.urlparse(str(getattr(bm1, "url", "") or "")).path
            path2 = urllib.parse.urlparse(str(getattr(bm2, "url", "") or "")).path
        except Exception:
            path1 = path2 = ""
        
        if path1 and path2:
            path_sim = 1 - (levenshtein_distance(path1, path2) / max(len(path1), len(path2)))
            scores.append(path_sim * 0.3)
        
        # Title similarity
        title_sim = self._title_similarity(getattr(bm1, "title", ""), getattr(bm2, "title", ""))
        scores.append(title_sim * 0.5)
        
        # Tag overlap
        tags1 = {str(tag).strip().lower() for tag in (getattr(bm1, "tags", None) or []) if str(tag).strip()}
        tags2 = {str(tag).strip().lower() for tag in (getattr(bm2, "tags", None) or []) if str(tag).strip()}
        if tags1 and tags2:
            common = tags1 & tags2
            total = tags1 | tags2
            tag_sim = len(common) / len(total) if total else 0
            scores.append(tag_sim * 0.2)
        
        return sum(scores)
    
    def _title_similarity(self, title1: str, title2: str) -> float:
        """Calculate title similarity using word overlap and edit distance"""
        t1 = str(title1 or "").lower()
        t2 = str(title2 or "").lower()
        
        # Word overlap (Jaccard)
        words1 = set(re.findall(r'\w+', t1))
        words2 = set(re.findall(r'\w+', t2))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        jaccard = len(intersection) / len(union)
        
        # Edit distance normalized
        max_len = max(len(t1), len(t2))
        edit_sim = 1 - (levenshtein_distance(t1, t2) / max_len) if max_len > 0 else 0
        
        return (jaccard * 0.6 + edit_sim * 0.4)


class AICostTracker:
    """Track AI API usage and estimated costs"""
    
    COST_FILE = DATA_DIR / "ai_costs.json"
    
    # Approximate costs per 1K tokens (as of mid-2026)
    COSTS = {
        "openai": {
            "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
            "gpt-4o": {"input": 0.0025, "output": 0.01},
            "gpt-4.1": {"input": 0.002, "output": 0.008},
            "gpt-4.1-mini": {"input": 0.0004, "output": 0.0016},
            "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
            "default": {"input": 0.00015, "output": 0.0006},
        },
        "anthropic": {
            "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
            "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
            "claude-3-5-haiku-20241022": {"input": 0.0008, "output": 0.004},
            "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
            "default": {"input": 0.003, "output": 0.015},
        },
        "google": {
            "gemini-2.0-flash": {"input": 0.0001, "output": 0.0004},
            "gemini-2.0-flash-lite": {"input": 0.000075, "output": 0.0003},
            "gemini-2.5-flash": {"input": 0.00015, "output": 0.0006},
            "gemini-2.5-pro": {"input": 0.00125, "output": 0.01},
            "gemini-1.5-flash": {"input": 0.000075, "output": 0.0003},
            "default": {"input": 0.0001, "output": 0.0004},
        },
        "groq": {
            "llama-3.3-70b-versatile": {"input": 0.00059, "output": 0.00079},
            "llama3-70b-8192": {"input": 0.00059, "output": 0.00079},
            "llama3-8b-8192": {"input": 0.00005, "output": 0.00008},
            "gemma2-9b-it": {"input": 0.0002, "output": 0.0002},
            "mixtral-8x7b-32768": {"input": 0.00024, "output": 0.00024},
            "default": {"input": 0.00059, "output": 0.00079},
        },
        "ollama": {
            "default": {"input": 0, "output": 0},
        },
    }
    
    def __init__(self):
        self.usage: Dict[str, Dict] = {}
        self._load_usage()

    @staticmethod
    def _clean_count(value) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _clean_cost(value) -> float:
        try:
            return max(0.0, float(value or 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _clean_usage(self, data) -> Dict[str, Dict]:
        """Coerce persisted usage metrics into the expected shape."""
        if not isinstance(data, dict):
            return {}

        cleaned: Dict[str, Dict] = {}
        for month, month_data in data.items():
            month_key = str(month or "").strip()
            if not re.fullmatch(r"\d{4}-\d{2}", month_key) or not isinstance(month_data, dict):
                continue

            cleaned_month: Dict[str, Dict] = {}
            for provider_model, metrics in month_data.items():
                key = str(provider_model or "").strip()
                if not key or not isinstance(metrics, dict):
                    continue
                cleaned_month[key] = {
                    "input_tokens": self._clean_count(metrics.get("input_tokens", 0)),
                    "output_tokens": self._clean_count(metrics.get("output_tokens", 0)),
                    "calls": self._clean_count(metrics.get("calls", 0)),
                    "cost": self._clean_cost(metrics.get("cost", 0.0)),
                }

            if cleaned_month:
                cleaned[month_key] = cleaned_month
        return cleaned
    
    def _load_usage(self):
        """Load usage data from file"""
        if self.COST_FILE.exists():
            try:
                with open(self.COST_FILE, 'r', encoding='utf-8') as f:
                    self.usage = self._clean_usage(json.load(f))
            except Exception as exc:
                log.warning(f"Could not load AI cost usage file: {exc}")
                self.usage = {}
    
    def _save_usage(self):
        """Save usage data to file"""
        self.COST_FILE.parent.mkdir(parents=True, exist_ok=True)
        _atomic_json_write(self.COST_FILE, self._clean_usage(self.usage))
    
    def record_usage(self, provider: str, model: str, 
                     input_tokens: int, output_tokens: int):
        """Record API usage"""
        provider = str(provider or "").strip().lower() or "unknown"
        model = str(model or "").strip() or "default"
        input_tokens = self._clean_count(input_tokens)
        output_tokens = self._clean_count(output_tokens)
        month_key = datetime.now().strftime("%Y-%m")
        
        if month_key not in self.usage:
            self.usage[month_key] = {}
        
        provider_key = f"{provider}/{model}"
        if provider_key not in self.usage[month_key]:
            self.usage[month_key][provider_key] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "calls": 0,
                "cost": 0.0
            }
        
        entry = self.usage[month_key][provider_key]
        entry["input_tokens"] += input_tokens
        entry["output_tokens"] += output_tokens
        entry["calls"] += 1
        
        # Calculate cost
        cost = self._calculate_cost(provider, model, input_tokens, output_tokens)
        entry["cost"] += cost
        
        self._save_usage()
    
    def _calculate_cost(self, provider: str, model: str,
                        input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for usage"""
        provider_costs = self.COSTS.get(str(provider or "").lower(), {})
        model_costs = provider_costs.get(str(model or ""), provider_costs.get("default", {"input": 0, "output": 0}))
        
        input_cost = (self._clean_count(input_tokens) / 1000) * self._clean_cost(model_costs.get("input", 0))
        output_cost = (self._clean_count(output_tokens) / 1000) * self._clean_cost(model_costs.get("output", 0))
        
        return input_cost + output_cost
    
    def get_monthly_summary(self, month: str = None) -> Dict:
        """Get usage summary for a month"""
        if month is None:
            month = datetime.now().strftime("%Y-%m")
        month = str(month or "").strip()
        
        month_data = self.usage.get(month, {})
        if not isinstance(month_data, dict):
            month_data = {}
        
        total_input = sum(self._clean_count(d.get("input_tokens", 0)) for d in month_data.values() if isinstance(d, dict))
        total_output = sum(self._clean_count(d.get("output_tokens", 0)) for d in month_data.values() if isinstance(d, dict))
        total_calls = sum(self._clean_count(d.get("calls", 0)) for d in month_data.values() if isinstance(d, dict))
        total_cost = sum(self._clean_cost(d.get("cost", 0.0)) for d in month_data.values() if isinstance(d, dict))
        
        return {
            "month": month,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_calls": total_calls,
            "total_cost": total_cost,
            "by_provider": month_data
        }
    
    def get_all_time_summary(self) -> Dict:
        """Get all-time usage summary"""
        total_input = 0
        total_output = 0
        total_calls = 0
        total_cost = 0.0
        
        for month_data in self.usage.values():
            if not isinstance(month_data, dict):
                continue
            for provider_data in month_data.values():
                if not isinstance(provider_data, dict):
                    continue
                total_input += self._clean_count(provider_data.get("input_tokens", 0))
                total_output += self._clean_count(provider_data.get("output_tokens", 0))
                total_calls += self._clean_count(provider_data.get("calls", 0))
                total_cost += self._clean_cost(provider_data.get("cost", 0.0))
        
        return {
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_calls": total_calls,
            "total_cost": total_cost,
            "months": len(self.usage)
        }
    
    def get_cost_report(self) -> str:
        """Generate a cost report"""
        summary = self.get_all_time_summary()
        monthly = self.get_monthly_summary()
        
        report = f"""AI Usage Report
══════════════════════════════════════

This Month ({monthly['month']}):
  Calls: {monthly['total_calls']}
  Input Tokens: {monthly['total_input_tokens']:,}
  Output Tokens: {monthly['total_output_tokens']:,}
  Estimated Cost: ${monthly['total_cost']:.4f}

All Time:
  Total Calls: {summary['total_calls']}
  Total Input Tokens: {summary['total_input_tokens']:,}
  Total Output Tokens: {summary['total_output_tokens']:,}
  Total Cost: ${summary['total_cost']:.4f}
"""
        return report
