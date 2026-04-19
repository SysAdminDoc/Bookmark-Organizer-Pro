"""Bookmark health scoring and smart duplicate merging.

- calculate_health_score(): 0-100 score based on 7 weighted factors
- merge_duplicate_bookmarks(): combines duplicates keeping best data

Inspired by Hoarder/Karakeep (health monitoring) and BrowserBookmarkChecker (merging).
"""

from datetime import datetime


def _safe_int(value, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _safe_str(value) -> str:
    return str(value or "")


def _tag_list(value) -> list:
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        return []

    tags = []
    seen = set()
    for tag in values:
        text = str(tag or "").strip()
        key = text.lower()
        if text and key not in seen:
            tags.append(text)
            seen.add(key)
    return tags


def _bookmark_dict(bookmark) -> dict:
    if hasattr(bookmark, "to_dict") and callable(bookmark.to_dict):
        data = bookmark.to_dict()
        return data if isinstance(data, dict) else {}
    return bookmark if isinstance(bookmark, dict) else {}


def calculate_health_score(bookmark) -> int:
    """Calculate a 0-100 health score for a bookmark.

    Factors:
    - Link validity (40 points)
    - Has title (10 points)
    - Has description/notes (10 points)
    - Has tags (10 points)
    - Recency — created/visited within 90 days (10 points)
    - Not stale — visited within last year (10 points)
    - Categorized — not in Uncategorized (10 points)
    """
    if bookmark is None:
        return 0

    score = 0

    # Link validity (40 pts)
    if bool(getattr(bookmark, "is_valid", True)):
        http_status = _safe_int(getattr(bookmark, "http_status", 0))
        if http_status == 200:
            score += 40
        elif http_status == 0:
            score += 30  # Not checked yet
        elif 300 <= http_status < 400:
            score += 25  # Redirect
        else:
            score += 10  # Non-200 but marked valid

    # Has meaningful title (10 pts)
    title = _safe_str(getattr(bookmark, "title", "")).strip()
    url = _safe_str(getattr(bookmark, "url", "")).strip()
    if title and title != url and len(title) > 3:
        score += 10

    # Has description or notes (10 pts)
    has_description = _safe_str(getattr(bookmark, "description", "")).strip()
    has_notes = _safe_str(getattr(bookmark, "notes", "")).strip()
    if has_description or has_notes:
        score += 10

    # Has tags (10 pts)
    tags = _tag_list(getattr(bookmark, "tags", []))
    if tags:
        score += min(10, len(tags) * 3)

    # Recency (10 pts)
    try:
        last_active = (
            _safe_str(getattr(bookmark, "last_visited", ""))
            or _safe_str(getattr(bookmark, "created_at", ""))
        )
        if last_active:
            dt = datetime.fromisoformat(last_active.replace('Z', '+00:00'))
            days = (datetime.now() - dt.replace(tzinfo=None)).days
            if days <= 30:
                score += 10
            elif days <= 90:
                score += 7
            elif days <= 180:
                score += 4
            elif days <= 365:
                score += 2
    except Exception:
        pass

    # Not stale (10 pts)
    try:
        if not bool(getattr(bookmark, "is_stale", True)):
            score += 10
    except Exception:
        pass

    # Categorized (10 pts)
    category = _safe_str(getattr(bookmark, "category", ""))
    if category and 'uncategorized' not in category.lower():
        score += 10

    return min(100, score)


def merge_duplicate_bookmarks(bookmarks: list) -> dict:
    """Merge a list of duplicate bookmarks into one canonical bookmark.

    Keeps:
    - Longest/best title (not a URL, not empty)
    - Earliest created_at
    - Latest modified_at / last_visited
    - Combined tags (union, case-insensitive)
    - Longest description/notes
    - Best favicon (non-empty)
    - Summed visit count
    - Category from most recently modified version
    - Pinned if any is pinned
    """
    if not bookmarks:
        return {}
    dicts = [_bookmark_dict(bookmark) for bookmark in bookmarks]
    dicts = [data for data in dicts if data.get("url")]
    if not dicts:
        return {}
    if len(dicts) == 1:
        merged = dict(dicts[0])
        merged['tags'] = _tag_list(merged.get('tags', []))
        merged['ai_tags'] = _tag_list(merged.get('ai_tags', []))
        merged['custom_data'] = (
            dict(merged.get('custom_data', {}))
            if isinstance(merged.get('custom_data'), dict)
            else {}
        )
        merged['visit_count'] = _safe_int(merged.get('visit_count', 0))
        return merged

    merged = dict(dicts[0])
    # Deep-copy mutable lists to prevent aliasing with the original Bookmark
    merged['tags'] = _tag_list(merged.get('tags', []))
    merged['ai_tags'] = _tag_list(merged.get('ai_tags', []))
    merged['custom_data'] = (
        dict(merged.get('custom_data', {}))
        if isinstance(merged.get('custom_data'), dict)
        else {}
    )
    merged['visit_count'] = _safe_int(merged.get('visit_count', 0))

    for d in dicts[1:]:

        # Best title
        title = _safe_str(d.get('title')).strip()
        merged_title = _safe_str(merged.get('title')).strip()
        if title and title != _safe_str(d.get('url')).strip():
            if (
                not merged_title
                or merged_title == _safe_str(merged.get('url')).strip()
                or len(title) > len(merged_title)
            ):
                merged['title'] = title

        # Earliest created_at
        created_at = _safe_str(d.get('created_at')).strip()
        if created_at and (not merged.get('created_at') or created_at < _safe_str(merged.get('created_at'))):
            merged['created_at'] = created_at

        # Latest modified_at
        modified_at = _safe_str(d.get('modified_at')).strip()
        if modified_at and (not merged.get('modified_at') or modified_at > _safe_str(merged.get('modified_at'))):
            merged['modified_at'] = modified_at

        # Latest last_visited
        last_visited = _safe_str(d.get('last_visited')).strip()
        if last_visited and (not merged.get('last_visited') or last_visited > _safe_str(merged.get('last_visited'))):
            merged['last_visited'] = last_visited

        # Union tags (case-insensitive)
        existing_tags = set(t.lower() for t in merged.get('tags', []))
        for tag in _tag_list(d.get('tags', [])):
            if tag.lower() not in existing_tags:
                merged.setdefault('tags', []).append(tag)
                existing_tags.add(tag.lower())

        # Union ai_tags
        existing_ai = set(t.lower() for t in merged.get('ai_tags', []))
        for tag in _tag_list(d.get('ai_tags', [])):
            if tag.lower() not in existing_ai:
                merged.setdefault('ai_tags', []).append(tag)
                existing_ai.add(tag.lower())

        # Longest description
        description = _safe_str(d.get('description')).strip()
        if description and len(description) > len(_safe_str(merged.get('description'))):
            merged['description'] = description

        # Longest notes
        notes = _safe_str(d.get('notes')).strip()
        if notes and len(notes) > len(_safe_str(merged.get('notes'))):
            merged['notes'] = notes

        # Best favicon
        if d.get('favicon_path') and not merged.get('favicon_path'):
            merged['favicon_path'] = d['favicon_path']
        if d.get('favicon_url') and not merged.get('favicon_url'):
            merged['favicon_url'] = d['favicon_url']
        if d.get('icon') and not merged.get('icon'):
            merged['icon'] = d['icon']

        # Sum visit counts
        merged['visit_count'] = (
            _safe_int(merged.get('visit_count', 0))
            + _safe_int(d.get('visit_count', 0))
        )

        # Pinned if any is pinned
        if bool(d.get('is_pinned')):
            merged['is_pinned'] = True

        # Category from most recently modified
        if modified_at >= _safe_str(merged.get('modified_at')):
            category = _safe_str(d.get('category')).strip()
            if category and 'uncategorized' not in category.lower():
                merged['category'] = category

    return merged
