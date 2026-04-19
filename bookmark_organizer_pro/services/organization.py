"""Bookmark organization helpers for smart tags, collections, and profiles."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.utils.runtime import atomic_json_write as _atomic_json_write


# =============================================================================
# Smart Tags (Auto-Tag Rules)
# =============================================================================
@dataclass
class SmartTagRule:
    """Rule for automatic tagging"""
    name: str
    tag: str
    conditions: List[Dict[str, str]]  # [{"field": "domain", "operator": "contains", "value": "github"}]
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def matches(self, bookmark: Bookmark) -> bool:
        """Check if bookmark matches all conditions"""
        if not self.enabled or not self.conditions:
            return False
        for condition in self.conditions:
            if not self._check_condition(bookmark, condition):
                return False
        return True
    
    def _check_condition(self, bookmark: Bookmark, condition: Dict) -> bool:
        """Check a single condition"""
        if not isinstance(condition, dict):
            return False

        field = str(condition.get("field", "") or "").strip().lower()
        operator = str(condition.get("operator", "") or "").strip().lower()
        value = str(condition.get("value", "") or "").strip()
        if not value:
            return False
        value_lower = value.lower()
        
        # Get field value
        if field == "domain":
            field_value = bookmark.domain.lower()
        elif field == "title":
            field_value = str(bookmark.title or "").lower()
        elif field == "url":
            field_value = str(bookmark.url or "").lower()
        elif field == "category":
            field_value = str(bookmark.category or "").lower()
        elif field == "notes":
            field_value = (bookmark.notes or "").lower()
        else:
            return False
        
        # Apply operator
        if operator == "contains":
            return value_lower in field_value
        elif operator == "starts_with":
            return field_value.startswith(value_lower)
        elif operator == "ends_with":
            return field_value.endswith(value_lower)
        elif operator == "equals":
            return field_value == value_lower
        elif operator == "regex":
            if len(value) > 250:
                return False
            try:
                return bool(re.search(value, field_value, re.IGNORECASE))
            except re.error:
                return False
        
        return False


class SmartTagManager:
    """Manages smart tagging rules"""
    
    RULES_FILE = DATA_DIR / "smart_tag_rules.json"
    
    def __init__(self):
        self.rules: List[SmartTagRule] = []
        self._load_rules()
    
    def _load_rules(self):
        """Load rules from file"""
        if self.RULES_FILE.exists():
            try:
                with open(self.RULES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.rules = []
                if isinstance(data, list):
                    for rule_data in data:
                        rule = self._rule_from_dict(rule_data)
                        if rule:
                            self.rules.append(rule)
            except Exception as e:
                log.warning(f"Could not load smart tag rules: {e}")
                self.rules = []
        else:
            # Default rules
            self.rules = [
                SmartTagRule(
                    name="GitHub Repos",
                    tag="github",
                    conditions=[{"field": "domain", "operator": "contains", "value": "github.com"}]
                ),
                SmartTagRule(
                    name="Documentation",
                    tag="docs",
                    conditions=[{"field": "url", "operator": "contains", "value": "/docs"}]
                ),
                SmartTagRule(
                    name="YouTube Videos",
                    tag="video",
                    conditions=[{"field": "domain", "operator": "contains", "value": "youtube.com"}]
                ),
                SmartTagRule(
                    name="Stack Overflow",
                    tag="stackoverflow",
                    conditions=[{"field": "domain", "operator": "contains", "value": "stackoverflow.com"}]
                ),
            ]
            self._save_rules()

    @staticmethod
    def _rule_from_dict(data) -> Optional[SmartTagRule]:
        """Build a valid smart tag rule from persisted data."""
        if not isinstance(data, dict):
            return None
        name = str(data.get("name") or "").strip()[:80]
        tag = str(data.get("tag") or "").strip()[:50]
        if not name or not tag:
            return None

        conditions = []
        for condition in data.get("conditions", []):
            if not isinstance(condition, dict):
                continue
            field = str(condition.get("field") or "").strip().lower()
            operator = str(condition.get("operator") or "").strip().lower()
            value = str(condition.get("value") or "").strip()
            if field and operator and value:
                conditions.append({"field": field, "operator": operator, "value": value})
        if not conditions:
            return None

        return SmartTagRule(
            name=name,
            tag=tag,
            conditions=conditions,
            enabled=bool(data.get("enabled", True)),
            created_at=str(data.get("created_at") or datetime.now().isoformat()),
        )
    
    def _save_rules(self):
        """Save rules to file"""
        self.RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        _atomic_json_write(self.RULES_FILE, [asdict(r) for r in self.rules])
    
    def add_rule(self, rule: SmartTagRule):
        """Add a new rule"""
        if not isinstance(rule, SmartTagRule) or not rule.name.strip() or not rule.tag.strip():
            return
        self.rules = [existing for existing in self.rules if existing.name != rule.name]
        self.rules.append(rule)
        self._save_rules()
    
    def remove_rule(self, name: str):
        """Remove a rule by name"""
        self.rules = [r for r in self.rules if r.name != name]
        self._save_rules()
    
    def apply_rules(self, bookmark: Bookmark) -> List[str]:
        """Apply all enabled rules to a bookmark and return matched tags"""
        tags = []
        existing = {str(tag).lower() for tag in bookmark.tags}
        for rule in self.rules:
            if rule.enabled and rule.matches(bookmark):
                tag_key = rule.tag.lower()
                if tag_key not in existing:
                    tags.append(rule.tag)
                    existing.add(tag_key)
        return tags
    
    def apply_to_all(self, bookmarks: List[Bookmark]) -> int:
        """Apply rules to all bookmarks, return count of tags added"""
        count = 0
        for bm in bookmarks:
            new_tags = self.apply_rules(bm)
            if new_tags:
                bm.tags.extend(new_tags)
                bm.modified_at = datetime.now().isoformat()
                count += len(new_tags)
        return count


# =============================================================================
# Collections/Folders (Named Groups)
# =============================================================================
@dataclass
class Collection:
    """A named collection of bookmarks"""
    id: str
    name: str
    description: str = ""
    icon: str = "📁"
    color: str = "#58a6ff"
    bookmark_ids: List[int] = field(default_factory=list)
    is_smart: bool = False
    smart_query: str = ""  # Search query for smart collections
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def count(self) -> int:
        return len(self.bookmark_ids)


class CollectionManager:
    """Manages bookmark collections"""
    
    COLLECTIONS_FILE = DATA_DIR / "collections.json"
    
    def __init__(self, bookmark_manager: BookmarkManager = None):
        self.bookmark_manager = bookmark_manager
        self.collections: Dict[str, Collection] = {}
        self._load_collections()
    
    def _load_collections(self):
        """Load collections from file"""
        if self.COLLECTIONS_FILE.exists():
            try:
                with open(self.COLLECTIONS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not isinstance(data, list):
                    return
                for coll_data in data:
                    coll = self._collection_from_dict(coll_data)
                    if coll:
                        self.collections[coll.id] = coll
            except Exception as e:
                log.warning(f"Could not load collections: {e}")

    @staticmethod
    def _collection_from_dict(data) -> Optional[Collection]:
        """Build a valid collection from persisted data."""
        if not isinstance(data, dict):
            return None
        coll_id = str(data.get("id") or "").strip()
        name = str(data.get("name") or "").strip()
        if not coll_id or not name:
            return None

        bookmark_ids = []
        for value in data.get("bookmark_ids", []):
            try:
                bookmark_ids.append(int(value))
            except (TypeError, ValueError):
                continue

        return Collection(
            id=coll_id[:120],
            name=name[:120],
            description=str(data.get("description") or "")[:1000],
            icon=str(data.get("icon") or "📁")[:8],
            color=str(data.get("color") or "#58a6ff")[:32],
            bookmark_ids=list(dict.fromkeys(bookmark_ids)),
            is_smart=bool(data.get("is_smart", False)),
            smart_query=str(data.get("smart_query") or "")[:500],
            created_at=str(data.get("created_at") or datetime.now().isoformat()),
            updated_at=str(data.get("updated_at") or datetime.now().isoformat()),
        )
    
    def _save_collections(self):
        """Save collections to file"""
        self.COLLECTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(c) for c in self.collections.values()]
        _atomic_json_write(self.COLLECTIONS_FILE, data)
    
    def create_collection(self, name: str, description: str = "", 
                         icon: str = "📁", color: str = "#58a6ff",
                         is_smart: bool = False, smart_query: str = "") -> Collection:
        """Create a new collection"""
        name = str(name or "").strip()
        if not name:
            raise ValueError("Collection name is required")
        coll_id = f"coll_{int(datetime.now().timestamp() * 1000)}_{int.from_bytes(os.urandom(2), 'big'):04x}"
        while coll_id in self.collections:
            coll_id = f"coll_{int(datetime.now().timestamp() * 1000)}_{int.from_bytes(os.urandom(2), 'big'):04x}"
        
        collection = Collection(
            id=coll_id,
            name=name[:120],
            description=str(description or "")[:1000],
            icon=str(icon or "📁")[:8],
            color=str(color or "#58a6ff")[:32],
            is_smart=is_smart,
            smart_query=str(smart_query or "")[:500]
        )
        
        self.collections[coll_id] = collection
        self._save_collections()
        return collection
    
    def delete_collection(self, coll_id: str):
        """Delete a collection"""
        if coll_id in self.collections:
            del self.collections[coll_id]
            self._save_collections()
    
    def add_to_collection(self, coll_id: str, bookmark_ids: List[int]):
        """Add bookmarks to a collection"""
        if coll_id in self.collections:
            coll = self.collections[coll_id]
            for bm_id in bookmark_ids:
                try:
                    normalized_id = int(bm_id)
                except (TypeError, ValueError):
                    continue
                if normalized_id not in coll.bookmark_ids:
                    coll.bookmark_ids.append(normalized_id)
            coll.updated_at = datetime.now().isoformat()
            self._save_collections()
    
    def remove_from_collection(self, coll_id: str, bookmark_ids: List[int]):
        """Remove bookmarks from a collection"""
        if coll_id in self.collections:
            coll = self.collections[coll_id]
            remove_ids = set()
            for bm_id in bookmark_ids:
                try:
                    remove_ids.add(int(bm_id))
                except (TypeError, ValueError):
                    continue
            coll.bookmark_ids = [bid for bid in coll.bookmark_ids if bid not in remove_ids]
            coll.updated_at = datetime.now().isoformat()
            self._save_collections()
    
    def get_collection_bookmarks(self, coll_id: str) -> List[Bookmark]:
        """Get all bookmarks in a collection"""
        if coll_id not in self.collections:
            return []
        
        coll = self.collections[coll_id]
        
        if coll.is_smart and self.bookmark_manager:
            # Smart collection - run query
            return self.bookmark_manager.search_bookmarks(coll.smart_query)
        else:
            # Static collection - return by IDs
            if self.bookmark_manager:
                return [
                    self.bookmark_manager.get_bookmark(bm_id)
                    for bm_id in coll.bookmark_ids
                    if self.bookmark_manager.get_bookmark(bm_id)
                ]
        return []
    
    def get_all_collections(self) -> List[Collection]:
        """Get all collections sorted by name"""
        return sorted(self.collections.values(), key=lambda c: c.name.lower())


# =============================================================================
# Frequently Used View (Visit Tracking)
# =============================================================================
class FrequentlyUsedManager:
    """Tracks and retrieves frequently used bookmarks"""
    
    def __init__(self, bookmark_manager: BookmarkManager):
        self.bookmark_manager = bookmark_manager
    
    def get_frequently_used(self, limit: int = 20, days: int = 30) -> List[Bookmark]:
        """Get most frequently visited bookmarks in time period"""
        cutoff = datetime.now() - timedelta(days=days)
        
        bookmarks_with_visits = []
        
        for bm in self.bookmark_manager.bookmarks.values():
            if bm.visit_count > 0:
                # Check if visited recently
                if bm.last_visited:
                    try:
                        last_visit = datetime.fromisoformat(bm.last_visited.replace('Z', '+00:00'))
                        if last_visit.replace(tzinfo=None) >= cutoff:
                            bookmarks_with_visits.append(bm)
                    except Exception:
                        bookmarks_with_visits.append(bm)
                else:
                    bookmarks_with_visits.append(bm)
        
        # Sort by visit count
        sorted_bms = sorted(bookmarks_with_visits, key=lambda b: b.visit_count, reverse=True)
        return sorted_bms[:limit]
    
    def get_trending(self, limit: int = 10) -> List[Bookmark]:
        """Get bookmarks with increasing visit frequency (trending)"""
        # This is a simplified version - could track daily visits for better trending
        recent = self.get_frequently_used(limit * 2, days=7)
        older = self.get_frequently_used(limit * 2, days=30)
        
        # Find bookmarks that are more popular recently
        recent_ids = {bm.id: i for i, bm in enumerate(recent)}
        older_ids = {bm.id: i for i, bm in enumerate(older)}
        
        trending = []
        for bm in recent:
            if bm.id in older_ids:
                # Higher rank in recent = trending
                rank_change = older_ids[bm.id] - recent_ids[bm.id]
                if rank_change > 0:
                    trending.append((bm, rank_change))
        
        trending.sort(key=lambda x: x[1], reverse=True)
        return [bm for bm, _ in trending[:limit]]


# =============================================================================
# Settings Profiles
# =============================================================================
@dataclass
class SettingsProfile:
    """A saved settings configuration"""
    name: str
    description: str = ""
    settings: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Settings that can be saved
    # - theme
    # - display_density
    # - default_category
    # - ai_provider
    # - view_mode
    # - sidebar_collapsed
    # - smart_filters


class SettingsProfileManager:
    """Manages settings profiles"""
    
    PROFILES_FILE = DATA_DIR / "settings_profiles.json"
    
    def __init__(self):
        self.profiles: Dict[str, SettingsProfile] = {}
        self._load_profiles()
    
    def _load_profiles(self):
        """Load profiles from file"""
        if self.PROFILES_FILE.exists():
            try:
                with open(self.PROFILES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    return
                for name, profile_data in data.items():
                    profile = self._profile_from_dict(profile_data, fallback_name=name)
                    if profile:
                        self.profiles[profile.name] = profile
            except Exception as e:
                log.warning(f"Could not load settings profiles: {e}")

    @staticmethod
    def _profile_from_dict(data, fallback_name: str = "") -> Optional[SettingsProfile]:
        """Build a settings profile from persisted or imported data."""
        if not isinstance(data, dict):
            return None
        name = str(data.get("name") or fallback_name or "").strip()
        if not name:
            return None
        settings = data.get("settings", {})
        if not isinstance(settings, dict):
            settings = {}
        return SettingsProfile(
            name=name[:80],
            description=str(data.get("description") or "")[:1000],
            settings=dict(settings),
            created_at=str(data.get("created_at") or datetime.now().isoformat()),
        )
    
    def _save_profiles(self):
        """Save profiles to file"""
        self.PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {name: asdict(p) for name, p in self.profiles.items()}
        _atomic_json_write(self.PROFILES_FILE, data)
    
    def save_profile(self, name: str, settings: Dict[str, Any], 
                     description: str = "") -> SettingsProfile:
        """Save current settings as a profile"""
        name = str(name or "").strip()
        if not name:
            raise ValueError("Profile name is required")
        if not isinstance(settings, dict):
            settings = {}
        profile = SettingsProfile(
            name=name[:80],
            description=str(description or "")[:1000],
            settings=dict(settings),
        )
        self.profiles[profile.name] = profile
        self._save_profiles()
        return profile
    
    def load_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """Load a profile's settings"""
        if name in self.profiles:
            return self.profiles[name].settings.copy()
        return None
    
    def delete_profile(self, name: str):
        """Delete a profile"""
        if name in self.profiles:
            del self.profiles[name]
            self._save_profiles()
    
    def export_profile(self, name: str, filepath: str):
        """Export a profile to file"""
        if name in self.profiles:
            target = Path(filepath)
            target.parent.mkdir(parents=True, exist_ok=True)
            _atomic_json_write(target, asdict(self.profiles[name]))
    
    def import_profile(self, filepath: str) -> Optional[SettingsProfile]:
        """Import a profile from file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                profile = self._profile_from_dict(data)
                if not profile:
                    return None
                self.profiles[profile.name] = profile
                self._save_profiles()
                return profile
        except Exception as e:
            log.warning(f"Could not import settings profile {filepath}: {e}")
            return None
    
    def get_all_profiles(self) -> List[SettingsProfile]:
        """Get all profiles"""
        return list(self.profiles.values())
