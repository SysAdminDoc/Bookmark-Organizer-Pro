"""Bookmark health scoring and smart duplicate merging.

- calculate_health_score(): 0-100 score based on 7 weighted factors
- merge_duplicate_bookmarks(): combines duplicates keeping best data

Inspired by Hoarder/Karakeep (health monitoring) and BrowserBookmarkChecker (merging).
"""

from datetime import datetime


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
    score = 0

    # Link validity (40 pts)
    if bookmark.is_valid:
        if bookmark.http_status == 200:
            score += 40
        elif bookmark.http_status == 0:
            score += 30  # Not checked yet
        elif 300 <= bookmark.http_status < 400:
            score += 25  # Redirect
        else:
            score += 10  # Non-200 but marked valid

    # Has meaningful title (10 pts)
    if bookmark.title and bookmark.title != bookmark.url and len(bookmark.title) > 3:
        score += 10

    # Has description or notes (10 pts)
    if bookmark.description or bookmark.notes:
        score += 10

    # Has tags (10 pts)
    if bookmark.tags:
        score += min(10, len(bookmark.tags) * 3)

    # Recency (10 pts)
    try:
        last_active = bookmark.last_visited or bookmark.created_at
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
    if not bookmark.is_stale:
        score += 10

    # Categorized (10 pts)
    if bookmark.category and 'uncategorized' not in bookmark.category.lower():
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
    if len(bookmarks) == 1:
        return bookmarks[0].to_dict()

    merged = bookmarks[0].to_dict()
    # Deep-copy mutable lists to prevent aliasing with the original Bookmark
    merged['tags'] = list(merged.get('tags', []))
    merged['ai_tags'] = list(merged.get('ai_tags', []))
    merged['custom_data'] = dict(merged.get('custom_data', {}))

    for bm in bookmarks[1:]:
        d = bm.to_dict()

        # Best title
        if d.get('title') and d['title'] != d.get('url', ''):
            if not merged.get('title') or merged['title'] == merged.get('url', '') or \
               len(d['title']) > len(merged['title']):
                merged['title'] = d['title']

        # Earliest created_at
        if d.get('created_at') and (not merged.get('created_at') or d['created_at'] < merged['created_at']):
            merged['created_at'] = d['created_at']

        # Latest modified_at
        if d.get('modified_at') and (not merged.get('modified_at') or d['modified_at'] > merged['modified_at']):
            merged['modified_at'] = d['modified_at']

        # Latest last_visited
        if d.get('last_visited') and (not merged.get('last_visited') or d['last_visited'] > merged['last_visited']):
            merged['last_visited'] = d['last_visited']

        # Union tags (case-insensitive)
        existing_tags = set(t.lower() for t in merged.get('tags', []))
        for tag in d.get('tags', []):
            if tag.lower() not in existing_tags:
                merged.setdefault('tags', []).append(tag)
                existing_tags.add(tag.lower())

        # Union ai_tags
        existing_ai = set(t.lower() for t in merged.get('ai_tags', []))
        for tag in d.get('ai_tags', []):
            if tag.lower() not in existing_ai:
                merged.setdefault('ai_tags', []).append(tag)
                existing_ai.add(tag.lower())

        # Longest description
        if d.get('description') and len(d['description']) > len(merged.get('description', '')):
            merged['description'] = d['description']

        # Longest notes
        if d.get('notes') and len(d['notes']) > len(merged.get('notes', '')):
            merged['notes'] = d['notes']

        # Best favicon
        if d.get('favicon_path') and not merged.get('favicon_path'):
            merged['favicon_path'] = d['favicon_path']
        if d.get('favicon_url') and not merged.get('favicon_url'):
            merged['favicon_url'] = d['favicon_url']
        if d.get('icon') and not merged.get('icon'):
            merged['icon'] = d['icon']

        # Sum visit counts
        merged['visit_count'] = merged.get('visit_count', 0) + d.get('visit_count', 0)

        # Pinned if any is pinned
        if d.get('is_pinned'):
            merged['is_pinned'] = True

        # Category from most recently modified
        if d.get('modified_at', '') >= merged.get('modified_at', ''):
            if d.get('category') and 'uncategorized' not in d.get('category', '').lower():
                merged['category'] = d['category']

    return merged
