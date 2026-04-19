"""AI-related background services and usage helpers."""

from __future__ import annotations

import re
import json
import threading
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable

from bookmark_organizer_pro.ai import AIClient, AIConfigManager, create_ai_client
from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.search import levenshtein_distance
from bookmark_organizer_pro.utils import safe_float
from bookmark_organizer_pro.utils.runtime import atomic_json_write as _atomic_json_write


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
            has_queue = bool(self._queue)
        if self._running or not has_queue:
            return
        
        self._running = True
        with self._lock:
            self._processed = 0
            self._results.clear()
            self._errors.clear()
        
        # Create AI client
        try:
            self._client = create_ai_client(self.ai_config)
        except Exception as e:
            self._running = False
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
        self._running = False
    
    def _worker(self):
        """Worker thread for processing bookmarks"""
        try:
            batch_size = max(1, min(50, int(self.ai_config.settings.get("batch_size", 5))))
        except (TypeError, ValueError):
            batch_size = 5
        try:
            rate_limit_delay = max(0.0, float(self.ai_config.settings.get("rate_limit_delay", 1.0)))
        except (TypeError, ValueError):
            rate_limit_delay = 1.0
        
        with self._lock:
            total = len(self._queue)
        
        while self._running:
            # Process in batches
            with self._lock:
                if not self._queue:
                    break
                batch = self._queue[:batch_size]
                del self._queue[:batch_size]
            
            for bookmark in batch:
                if not self._running:
                    break
                
                try:
                    # Get AI categorization and tags
                    result = self._process_bookmark(bookmark)
                    with self._lock:
                        self._results[bookmark.id] = result
                    
                    # Apply results
                    if result.get("category"):
                        bookmark.category = result["category"]
                        bookmark.ai_categorized = True
                        bookmark.ai_confidence = result.get("confidence", 0.0)
                    
                    if result.get("tags"):
                        existing = {str(tag).lower() for tag in bookmark.tags}
                        for tag in result["tags"]:
                            tag_text = str(tag or "").strip()
                            if tag_text and tag_text.lower() not in existing:
                                bookmark.tags.append(tag_text)
                                existing.add(tag_text.lower())
                    
                    if result.get("summary"):
                        if not bookmark.notes:
                            bookmark.notes = result["summary"]
                    
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
                
                # Rate limiting
                if rate_limit_delay:
                    time.sleep(rate_limit_delay)
        
        self._running = False
        if self.on_complete:
            try:
                with self._lock:
                    processed = self._processed
                self.on_complete(True, f"Processed {processed} bookmarks")
            except Exception as callback_exc:
                log.warning(f"AI batch completion callback failed: {callback_exc}")
    
    def _process_bookmark(self, bookmark: Bookmark) -> Dict:
        """Process a single bookmark with AI"""
        result = {}
        
        # Build prompt for categorization + tags + summary
        prompt = f"""Analyze this bookmark and provide:
1. Best category from common bookmark categories
2. 3-5 relevant tags (single words, lowercase)
3. A brief 1-sentence summary

URL: {bookmark.url}
Title: {bookmark.title}
Current Category: {bookmark.category}
Domain: {bookmark.domain}

Respond in JSON format:
{{"category": "...", "tags": ["...", "..."], "summary": "...", "confidence": 0.0-1.0}}"""
        
        try:
            response = self._client.categorize_bookmark(
                bookmark.url, bookmark.title, []
            )
            
            if response:
                category = str(response.get("category") or bookmark.category).strip()
                result["category"] = category or bookmark.category
                result["confidence"] = max(0.0, min(1.0, safe_float(response.get("confidence", 0.5), 0.5)))
                tags = response.get("tags", [])
                if isinstance(tags, str):
                    tags = tags.split(",")
                result["tags"] = [
                    str(tag).strip()
                    for tag in (tags or [])
                    if str(tag).strip()
                ][:10]
                result["summary"] = str(response.get("summary") or "")[:1000]
        except Exception:
            pass
        
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
    
    def __init__(self, ai_config: AIConfigManager):
        self.ai_config = ai_config
        self._cache: Dict[str, List[str]] = {}
    
    def suggest_tags(self, bookmark: Bookmark, existing_tags: List[str] = None) -> List[str]:
        """Get AI-suggested tags for a bookmark"""
        cache_key = f"{bookmark.url}:{bookmark.title}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            client = create_ai_client(self.ai_config)
            
            prompt = f"""Suggest 5-7 relevant tags for this bookmark.
Tags should be:
- Single words or short phrases
- Lowercase
- Descriptive of content, topic, or purpose
- Not duplicate existing tags: {existing_tags or []}

URL: {bookmark.url}
Title: {bookmark.title}
Domain: {bookmark.domain}
Notes: {bookmark.notes[:200] if bookmark.notes else 'None'}

Return only a JSON array of tag strings: ["tag1", "tag2", ...]"""
            
            # Use the client's categorize method but parse for tags
            response = client.categorize_bookmark(bookmark.url, bookmark.title, [])
            
            if response and "tags" in response:
                tags = response["tags"]
                self._cache[cache_key] = tags
                return tags
        except Exception:
            pass
        
        # Fallback: generate from content
        return self._generate_fallback_tags(bookmark)
    
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
    
    # Approximate costs per 1K tokens (as of 2024)
    COSTS = {
        "openai": {
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-4-turbo": {"input": 0.01, "output": 0.03},
            "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
        },
        "anthropic": {
            "claude-3-opus": {"input": 0.015, "output": 0.075},
            "claude-3-sonnet": {"input": 0.003, "output": 0.015},
            "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
        },
        "google": {
            "gemini-pro": {"input": 0.00025, "output": 0.0005},
        },
        "groq": {
            "llama2-70b": {"input": 0.0007, "output": 0.0008},
            "mixtral-8x7b": {"input": 0.00027, "output": 0.00027},
        },
        "ollama": {
            "default": {"input": 0, "output": 0},  # Local, no cost
        }
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
