"""URL canonicalization for deduplication.

Academic-grade URL normalization inspired by:
- URL Normalization for De-duplication of Web Pages (ACM CIKM 2009)
- BrowserBookmarkChecker's URL canonicalization pipeline
"""

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


# Tracking parameters to strip during normalization (60+ entries)
TRACKING_PARAMS = frozenset({
    # Google Analytics / Ads
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'utm_id', 'utm_source_platform', 'utm_creative_format', 'utm_marketing_tactic',
    'gclid', 'gclsrc', 'dclid', 'gbraid', 'wbraid', '_ga', '_gl', '_gid',
    # Facebook / Meta
    'fbclid', 'fb_action_ids', 'fb_action_types', 'fb_source', 'fb_ref',
    'action_object_map', 'action_type_map', 'action_ref_map',
    # Microsoft
    'msclkid', 'mkt_tok',
    # Twitter / X
    'twclid',
    # Instagram
    'igshid', 'igsh',
    # YouTube
    'si', 'feature', 'pp', 'embeds_referring_euri', 'source_ve_path',
    # Mailchimp
    'mc_cid', 'mc_eid',
    # HubSpot
    'hsa_cam', 'hsa_grp', 'hsa_mt', 'hsa_src', 'hsa_ad', 'hsa_acc',
    'hsa_net', 'hsa_ver', 'hsa_la', 'hsa_ol', 'hsa_kw', 'hsa_tgt',
    # Generic tracking
    'ref', 'source', 'ref_src', 'ref_url', 'referrer',
    'clickid', 'click_id', 'campaign_id', 'ad_id', 'adgroup_id',
    'yclid', '_hsenc', '_hsmi', '_openstat', 'spm',
})

# Default index filenames to strip from paths
INDEX_FILES = frozenset({
    'index.html', 'index.htm', 'index.php', 'index.asp', 'index.aspx',
    'index.jsp', 'index.shtml', 'index.cfm', 'default.html', 'default.htm',
    'default.asp', 'default.aspx',
})


def normalize_url(url: str) -> str:
    """Normalize a URL for canonical deduplication.

    Applies RFC 3986 normalization plus practical web heuristics:
    - Lowercase scheme and host
    - Strip www. prefix
    - Remove default ports (80 for http, 443 for https)
    - Remove trailing slash
    - Remove fragment (#...)
    - Remove tracking/analytics query parameters
    - Sort remaining query parameters
    - Remove default index files (index.html, etc.)
    - Upgrade http to https
    """
    if not url:
        return url

    raw = url.strip()
    try:
        parsed = urlparse(raw)
    except Exception:
        return raw.lower().rstrip('/')

    if not parsed.scheme and not parsed.netloc:
        if any(ch.isspace() for ch in raw):
            return raw.lower().rstrip('/')
        reparsed = urlparse(f"https://{raw}")
        if reparsed.hostname:
            parsed = reparsed
        else:
            return raw.lower().rstrip('/')

    scheme = (parsed.scheme or 'https').lower()
    host = (parsed.hostname or '').lower()
    if not host:
        return raw.lower().rstrip('/')
    if host.startswith('www.'):
        host = host[4:]
    try:
        port = parsed.port
    except ValueError:
        port = None

    # Remove default ports
    if (scheme == 'http' and port == 80) or (scheme == 'https' and port == 443):
        port = None

    # Upgrade http to https
    if scheme == 'http':
        scheme = 'https'

    # Build netloc
    netloc = host
    if port:
        netloc = f"{host}:{port}"
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        netloc = f"{userinfo}@{netloc}"

    # Normalize path
    path = parsed.path or '/'

    # Remove default index files
    path_lower = path.lower()
    for idx_file in INDEX_FILES:
        if path_lower.endswith('/' + idx_file):
            path = path[:-(len(idx_file))]
            break

    # Remove trailing slash
    path = path.rstrip('/') or ''

    # Filter and sort query parameters
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {
            k: v for k, v in params.items()
            if k.lower() not in TRACKING_PARAMS
        }
        query = urlencode(sorted(filtered.items()), doseq=True)
    else:
        query = ''

    # Drop fragment entirely
    return urlunparse((scheme, netloc, path, parsed.params, query, ''))
