"""
Platform profile resolvers.

Each resolver accepts a username and returns a list of discovered identities:
    [{"value": str, "type": "email"|"username", "source": str, "hint_platform": str|None}, ...]

Only platforms with freely-accessible APIs or public profile data are implemented.
For all other platforms, the rule-based extraction system (resolve_via_rules)
acts as a generic fallback using cached LLM-learned selectors.
"""
import re
from datetime import datetime, timezone
import json
from urllib.parse import urlparse

import aiohttp

GITHUB_HEADERS = {
    "User-Agent": "osint-tool/1.0",
    "Accept": "application/vnd.github+json",
}

EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')

# Patterns to extract (username, platform) from a social profile URL.
# Each pattern stops at a slash, query string, or end-of-string so we don't
# accidentally grab path segments as usernames.
_SOCIAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'(?:twitter|x)\.com/(?:@)?([\w]{1,50})(?:[/?#]|$)'), 'Twitter/X'),
    (re.compile(r'github\.com/([\w][\w-]{0,38})(?:[/?#]|$)'), 'GitHub'),
    (re.compile(r'instagram\.com/([\w.]{1,30})(?:[/?#]|$)'), 'Instagram'),
    (re.compile(r'reddit\.com/u(?:ser)?/([\w-]{3,20})(?:[/?#]|$)'), 'Reddit'),
    (re.compile(r'pinterest\.com/([\w_]{3,30})(?:[/?#]|$)'), 'Pinterest'),
    (re.compile(r'linkedin\.com/in/([\w-]{3,100})(?:[/?#]|$)'), 'LinkedIn'),
    (re.compile(r'tiktok\.com/@([\w.]{2,24})(?:[/?#]|$)'), 'TikTok'),
    (re.compile(r'youtube\.com/@([\w-]{3,30})(?:[/?#]|$)'), 'YouTube'),
    (re.compile(r'medium\.com/@([\w-]{3,50})(?:[/?#]|$)'), 'Medium'),
    (re.compile(r'steamcommunity\.com/id/([\w-]{2,32})(?:[/?#]|$)'), 'Steam'),
]

# Generic URL path segments that are navigation, not usernames.
_SKIP_USERNAMES = frozenset({
    'share', 'intent', 'status', 'photo', 'video', 'hashtag', 'search',
    'explore', 'login', 'signup', 'watch', 'channel', 'user', 'profile',
    'settings', 'help', 'about', 'home', 'feed', 'notifications', 'messages',
})


def extract_from_urls(urls: list[str]) -> list[dict]:
    """Parse a list of URLs and extract social platform usernames."""
    results = []
    seen: set[tuple[str, str]] = set()
    for url in urls:
        for pattern, platform in _SOCIAL_PATTERNS:
            m = pattern.search(url)
            if m:
                username = m.group(1).lstrip('@')
                key = (username.lower(), platform)
                if username.lower() not in _SKIP_USERNAMES and key not in seen:
                    seen.add(key)
                    results.append({
                        'value': username,
                        'type': 'username',
                        'hint_platform': platform,
                        'source': f'URL: {url}',
                    })
                break
    return results


def resolve_gravatar(profile) -> list[dict]:
    """Extract identities from an already-fetched GravatarProfile."""
    if not profile:
        return []
    identities = []

    if profile.urls:
        for identity in extract_from_urls(profile.urls):
            identity['source'] = 'Gravatar linked URL'
            identities.append(identity)

    # Scan free-text fields for email addresses
    for text in filter(None, [profile.about, profile.display_name]):
        for email in EMAIL_RE.findall(text):
            identities.append({
                'value': email,
                'type': 'email',
                'hint_platform': None,
                'source': 'Gravatar profile text',
            })

    return identities


async def resolve_github(username: str) -> list[dict]:
    """Extract identities from a GitHub user profile via the REST API."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.github.com/users/{username}",
                headers=GITHUB_HEADERS,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
    except Exception:
        return []

    identities = []

    if email := (data.get('email') or '').strip():
        if EMAIL_RE.match(email):
            identities.append({
                'value': email,
                'type': 'email',
                'hint_platform': None,
                'source': 'GitHub public email',
            })

    if twitter := (data.get('twitter_username') or '').lstrip('@'):
        if twitter:
            identities.append({
                'value': twitter,
                'type': 'username',
                'hint_platform': 'Twitter/X',
                'source': 'GitHub Twitter field',
            })

    if blog := (data.get('blog') or ''):
        for identity in extract_from_urls([blog]):
            identity['source'] = 'GitHub blog link'
            identities.append(identity)

    return identities


_PINTEREST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


async def resolve_pinterest(username: str) -> list[dict]:
    """
    Try to extract the canonical Pinterest username from a profile page.

    Pinterest profile URLs use the same slug as the username, but older
    accounts or migrated accounts may have a different handle shown on-page.
    We try three extraction strategies in order:
      1. og:url meta tag  — gives the canonical profile URL
      2. Title tag        — often "Display Name (@username) | Pinterest"
      3. JSON blob search — Pinterest embeds profile data as inline JSON
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://www.pinterest.com/{username}/",
                headers=_PINTEREST_HEADERS,
                timeout=aiohttp.ClientTimeout(total=12),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
    except Exception:
        return []

    found: str | None = None

    # Strategy 1: og:url meta tag
    # e.g. <meta property="og:url" content="https://www.pinterest.com/actual_user/" />
    m = re.search(r'<meta[^>]+og:url[^>]*>', html, re.IGNORECASE)
    if m:
        cm = re.search(r'content=["\']https?://(?:www\.)?pinterest\.com/([^/"?\']+)', m.group(0))
        if cm:
            found = cm.group(1)

    # Strategy 2: title tag — "Name (@handle) | Pinterest"
    if not found:
        m = re.search(r'<title[^>]*>([^<]{1,200})</title>', html, re.IGNORECASE)
        if m:
            # Look for an @handle in parentheses
            hm = re.search(r'\(@?([\w.]{3,50})\)', m.group(1))
            if hm:
                found = hm.group(1)

    # Strategy 3: JSON blob — Pinterest embeds profile JSON as
    # {"username":"actual_user", ...} in inline <script> tags
    if not found:
        m = re.search(r'"username"\s*:\s*"([\w.]{3,50})"', html)
        if m:
            found = m.group(1)

    if not found or found.lower() in _SKIP_USERNAMES:
        return []

    # Only report if it differs from what we searched
    if found.lower() == username.lower():
        return []

    return [{
        'value': found,
        'type': 'username',
        'hint_platform': 'Pinterest',
        'source': 'Pinterest profile page',
    }]


# Dispatcher — map platform display name → async resolver function.
_RESOLVERS: dict[str, any] = {
    'GitHub': resolve_github,
    'Pinterest': resolve_pinterest,
}

MAX_FAIL_BEFORE_SKIP = 3


async def resolve_platform(
    platform,
    username: str,
    html_body: str | None = None,
    url: str | None = None,
) -> tuple[list[dict], dict | None]:
    """Run the resolver for a platform, then rule-based extraction if HTML available.

    Hand-written resolvers always run first.  Rule-based extraction (cached
    selectors + LLM fallback) runs on any HTML we captured, merging results.

    Returns (identities, extraction_activity) where extraction_activity is set
    when HTML-based extraction ran (cached rules, LLM, skip, or failure).
    """
    name = platform.value if hasattr(platform, 'value') else str(platform)

    identities: list[dict] = []
    extraction_activity: dict | None = None

    fn = _RESOLVERS.get(name)
    if fn is not None:
        identities = await fn(username)

    if html_body and url:
        rule_identities, activity = await resolve_via_rules(url, html_body, username)
        identities.extend(rule_identities)
        if activity is not None:
            extraction_activity = activity
            extraction_activity["platform"] = name

    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for ident in identities:
        key = (ident["value"].lower(), ident.get("type", ""))
        if key not in seen:
            seen.add(key)
            unique.append(ident)

    return unique, extraction_activity


def _llm_preview(llm_result: dict) -> str:
    """Compact JSON for UI (truncated)."""
    slim = {
        "identities": llm_result.get("identities", []),
        "methods": llm_result.get("methods", []),
    }
    text = json.dumps(slim, indent=2, ensure_ascii=False)
    if len(text) > 4000:
        return text[:4000] + "\n… [truncated]"
    return text


async def resolve_via_rules(
    profile_url: str, html_body: str, username: str,
) -> tuple[list[dict], dict | None]:
    """Extract identities using cached rules or LLM learning for the domain.

    Second return value is telemetry for the UI (SSE), or None if nothing to report.
    """
    from osint_tool.data.rule_cache import get_rule_cache
    from osint_tool.data.rule_schema import ExtractionMethod, SiteRule
    from osint_tool.modules.extraction_runner import run_extraction
    from osint_tool.modules.html_cleaner import clean_html
    from osint_tool.modules.llm_extractor import has_api_key, llm_extract

    domain = urlparse(profile_url).netloc.lstrip("www.")
    if not domain:
        return [], None

    cache = get_rule_cache()
    rule = cache.get(domain)

    cleaned_html, json_ld_blocks, fingerprint = clean_html(html_body)

    # Try cached rule if it exists, isn't skipped, and isn't flagged
    if rule and not rule.skip and not rule.needs_relearn:
        result = run_extraction(rule, cleaned_html, json_ld_blocks, fingerprint)
        if not result.stale:
            return result.identities, {
                "domain": domain,
                "mode": "cached_rules",
                "identities_found": len(result.identities),
                "methods_in_rule": len(rule.methods),
                "stale": False,
                "message": f"Used cached selectors for {domain} — {len(result.identities)} identity/ies.",
            }
        # Rule is stale — fall through to LLM re-learn

    if rule and rule.skip:
        return [], {
            "domain": domain,
            "mode": "skipped",
            "reason": rule.skip_reason or "site marked skip",
            "message": f"Skipped {domain} — {rule.skip_reason or 'extraction disabled for this domain'}.",
        }

    if not has_api_key():
        return [], {
            "domain": domain,
            "mode": "no_api_key",
            "message": f"No API key — cannot run LLM extraction for {domain} (bundled rules still apply if present).",
        }

    # LLM extraction (first visit or stale rule)
    llm_result = await llm_extract(domain, cleaned_html, json_ld_blocks)

    if llm_result is None:
        fail_count = 0
        if rule:
            fail_count = cache.increment_fail_count(domain)
            if fail_count >= MAX_FAIL_BEFORE_SKIP:
                cache.mark_skip(domain, f"LLM extraction failed {fail_count} consecutive times")
        return [], {
            "domain": domain,
            "mode": "llm_failed",
            "fail_count": fail_count,
            "message": f"LLM call failed or returned invalid JSON for {domain}.",
        }

    methods = [ExtractionMethod.from_dict(m) for m in llm_result.get("methods", [])]
    new_rule = SiteRule(
        domain=domain,
        version=(rule.version + 1) if rule else 1,
        updated_at=datetime.now(timezone.utc).isoformat(),
        fingerprint=fingerprint,
        methods=methods,
        needs_relearn=False,
        fail_count=0,
    )
    cache.save_rule(new_rule)

    identities: list[dict] = []
    for ident in llm_result.get("identities", []):
        if not ident.get("value"):
            continue
        identities.append({
            "value": ident["value"],
            "type": ident.get("type", "username"),
            "hint_platform": ident.get("hint_platform"),
            "source": f"LLM extraction ({domain})",
        })

    return identities, {
        "domain": domain,
        "mode": "llm",
        "identities_found": len(identities),
        "methods_learned": len(methods),
        "preview": _llm_preview(llm_result),
        "message": (
            f"LLM extraction for {domain} — {len(identities)} identity/ies, "
            f"{len(methods)} rule method(s) saved to local cache."
        ),
    }
