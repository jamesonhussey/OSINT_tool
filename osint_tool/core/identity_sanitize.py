"""
Normalize and validate candidate identities before queueing or displaying them.

Drops obvious non-handles (raw asset paths, navigation tokens, unparseable URLs)
while allowing known profile URL patterns to collapse to usernames.
"""
from __future__ import annotations

import re

from osint_tool.core.engine import is_email
from osint_tool.core.models import Platform
from osint_tool.modules.resolvers import extract_from_urls

# Path / UI tokens that are never useful as cross-platform seeds.
_NOISE_USERNAMES = frozenset({
    "share", "intent", "status", "photo", "video", "hashtag", "search",
    "explore", "login", "signup", "watch", "channel", "user", "profile",
    "settings", "help", "about", "home", "feed", "notifications", "messages",
    "assets", "static", "public", "config", "cdn", "media", "dist", "build",
    "src", "js", "css", "img", "images", "fonts", "favicon", "robots",
    "api", "v1", "v2", "graphql", "oauth", "callback",
    # Experimentation / analytics tokens that appear in page HTML (e.g. Twitch + Eppo).
    "eppo",
})

_USER_RE = re.compile(r"^[\w.\-]{2,64}$")


def _brand_tokens_for_platform_label(name: str) -> frozenset[str]:
    """Lowercase tokens that are just the site's brand, not a person handle."""
    alnum = "".join(c for c in name.lower() if c.isalnum())
    tokens: set[str] = set()
    if alnum:
        tokens.add(alnum)
    if name == "Twitter/X":
        tokens.update({"twitter", "x", "twitterx"})
    elif name == "Docker Hub":
        tokens.add("docker")
    elif name == "npm":
        return frozenset({"npm"})
    elif name == "Dev.to":
        return frozenset({"devto"})
    return frozenset(tokens)


# Maps Platform.value (and matching hint strings) → bogus self-referential handles.
_BRAND_BY_PLATFORM: dict[str, frozenset[str]] = {
    p.value: _brand_tokens_for_platform_label(p.value) for p in Platform
}


def is_username_just_platform_brand(
    value: str,
    *,
    source_platform: str | None = None,
    hint_platform: str | None = None,
) -> bool:
    """
    True if value is only the source site's own name (e.g. \"github\" extracted from GitHub).

    Emails are never treated as brand noise. Checks source_platform and optional
    hint_platform (e.g. Gravatar link target).
    """
    if not value or is_email(value):
        return False
    v = value.strip().lower()
    if not v:
        return True

    def matches_label(label: str | None) -> bool:
        if not label:
            return False
        label = label.strip()
        brands = _BRAND_BY_PLATFORM.get(label)
        if brands is not None:
            return v in brands
        alnum = "".join(c for c in label.lower() if c.isalnum())
        return len(alnum) >= 3 and v == alnum

    return matches_label(source_platform) or matches_label(hint_platform)


def sanitize_discovery_identity(raw: str) -> str | None:
    """
    Return a normalized seed value, or None if the string should not be queued.

    Emails are returned trimmed. Usernames are normalized; full URLs are parsed
    when they match known profile patterns (via extract_from_urls).
    """
    if not raw:
        return None
    s = raw.strip()
    if not s or len(s) > 200:
        return None

    if is_email(s):
        return s

    lower = s.lower()

    # Explicit URL / www — try to extract a handle via social patterns.
    if lower.startswith(("http://", "https://", "www.")) or "://" in s:
        url = s
        if lower.startswith("www."):
            url = "https://" + s
        extracted = extract_from_urls([url])
        if extracted:
            cand = extracted[0]["value"].strip()
            return _finalize_username(cand)
        return None

    # Looks like a host/path without scheme (e.g. github.com/foo)
    if "/" in s and "." in s.split("/")[0]:
        trial = "https://" + s.lstrip("/")
        extracted = extract_from_urls([trial])
        if extracted:
            return _finalize_username(extracted[0]["value"].strip())
        return None

    # Bare path segments or Windows paths — not a portable handle.
    if "/" in s or "\\" in s:
        return None

    return _finalize_username(s)


def _finalize_username(s: str) -> str | None:
    if not s:
        return None
    if len(s) < 2 or len(s) > 64:
        return None
    key = s.lower()
    if key in _NOISE_USERNAMES:
        return None
    if not _USER_RE.match(s):
        return None
    return s
