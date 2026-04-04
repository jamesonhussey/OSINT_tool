"""
Platform profile resolvers.

Each resolver accepts a username and returns a list of discovered identities:
    [{"value": str, "type": "email"|"username", "source": str, "hint_platform": str|None}, ...]

Only platforms with freely-accessible APIs or public profile data are implemented.
"""
import re
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


async def resolve_platform(platform, username: str) -> list[dict]:
    """Run the resolver for a platform, if one exists. Returns [] otherwise."""
    name = platform.value if hasattr(platform, 'value') else str(platform)
    fn = _RESOLVERS.get(name)
    if fn is None:
        return []
    return await fn(username)
