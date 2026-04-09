"""Extraction runner.

Applies cached extraction rules against HTML content using the priority chain:
JSON-LD > CSS selectors > XPath > Regex.

Includes staleness detection via selector failure and fingerprint drift.
"""
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from lxml import etree

from osint_tool.data.rule_schema import ExtractionMethod, IdentityType, MethodType, SiteRule


@dataclass
class ExtractionResult:
    identities: list[dict] = field(default_factory=list)
    stale: bool = False
    methods_tried: int = 0
    methods_succeeded: int = 0


_METHOD_PRIORITY = {
    MethodType.JSON_LD: 0,
    MethodType.CSS: 1,
    MethodType.XPATH: 2,
    MethodType.REGEX: 3,
}


def run_extraction(
    rule: SiteRule,
    cleaned_html: str,
    json_ld_blocks: list[dict],
    current_fingerprint: str,
) -> ExtractionResult:
    """Apply a site rule's methods against pre-cleaned HTML.

    Returns extracted identities and whether the rule appears stale.
    """
    fingerprint_stale = bool(rule.fingerprint and current_fingerprint != rule.fingerprint)

    all_identities: list[dict] = []
    methods_tried = 0
    methods_succeeded = 0

    sorted_methods = sorted(rule.methods, key=lambda m: _METHOD_PRIORITY.get(m.type, 99))

    for method in sorted_methods:
        methods_tried += 1
        results = _apply_method(method, cleaned_html, json_ld_blocks)
        if results:
            methods_succeeded += 1
            all_identities.extend(results)

    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for ident in all_identities:
        key = (ident["value"].lower(), ident.get("type", ""))
        if key not in seen:
            seen.add(key)
            unique.append(ident)

    stale = (methods_tried > 0 and methods_succeeded == 0) or fingerprint_stale

    return ExtractionResult(
        identities=unique,
        stale=stale,
        methods_tried=methods_tried,
        methods_succeeded=methods_succeeded,
    )


# ---------------------------------------------------------------------------
# Per-method extractors
# ---------------------------------------------------------------------------

def _apply_method(
    method: ExtractionMethod,
    html: str,
    json_ld_blocks: list[dict],
) -> list[dict]:
    try:
        if method.type == MethodType.JSON_LD:
            return _extract_json_ld(method, json_ld_blocks)
        elif method.type == MethodType.CSS:
            return _extract_css(method, html)
        elif method.type == MethodType.XPATH:
            return _extract_xpath(method, html)
        elif method.type == MethodType.REGEX:
            return _extract_regex(method, html)
    except Exception:
        return []
    return []


def _extract_json_ld(method: ExtractionMethod, blocks: list[dict]) -> list[dict]:
    results: list[dict] = []
    for block in blocks:
        for val in _resolve_json_path(block, method.path or ""):
            ident = _make_identity(str(val), method)
            if ident:
                results.append(ident)
    return results


def _resolve_json_path(data: dict, path: str) -> list:
    """Minimal JSONPath resolver.  Supports $.key, $.key[*], $.key.subkey."""
    if not path or not path.startswith("$"):
        return []
    parts = path.lstrip("$").lstrip(".").split(".")
    current: list = [data]
    for part in parts:
        next_vals: list = []
        if part.endswith("[*]"):
            key = part[:-3]
            for item in current:
                val = item.get(key, []) if isinstance(item, dict) else []
                if isinstance(val, list):
                    next_vals.extend(val)
        else:
            for item in current:
                if isinstance(item, dict) and part in item:
                    next_vals.append(item[part])
        current = next_vals
    return current


def _extract_css(method: ExtractionMethod, html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    results: list[dict] = []
    for el in soup.select(method.selector or ""):
        val = el.get(method.attr, "") if method.attr else el.get_text(strip=True)
        if val:
            ident = _make_identity(str(val), method)
            if ident:
                results.append(ident)
    return results


def _extract_xpath(method: ExtractionMethod, html: str) -> list[dict]:
    try:
        tree = etree.HTML(html)
    except Exception:
        return []
    results: list[dict] = []
    for val in tree.xpath(method.expr or ""):
        text = val if isinstance(val, str) else (getattr(val, "text", None) or str(val))
        if text:
            ident = _make_identity(text.strip(), method)
            if ident:
                results.append(ident)
    return results


def _extract_regex(method: ExtractionMethod, html: str) -> list[dict]:
    results: list[dict] = []
    try:
        for m in re.finditer(method.pattern or "", html):
            val = m.group(method.group)
            if val:
                ident = _make_identity(val, method)
                if ident:
                    results.append(ident)
    except (re.error, IndexError):
        pass
    return results


# ---------------------------------------------------------------------------
# Identity construction + URL parsing
# ---------------------------------------------------------------------------

_URL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?:twitter|x)\.com/(?:@)?([\w]{1,50})(?:[/?#]|$)"), "Twitter/X"),
    (re.compile(r"github\.com/([\w][\w-]{0,38})(?:[/?#]|$)"), "GitHub"),
    (re.compile(r"instagram\.com/([\w.]{1,30})(?:[/?#]|$)"), "Instagram"),
    (re.compile(r"reddit\.com/u(?:ser)?/([\w-]{3,20})(?:[/?#]|$)"), "Reddit"),
    (re.compile(r"pinterest\.com/([\w_]{3,30})(?:[/?#]|$)"), "Pinterest"),
    (re.compile(r"linkedin\.com/in/([\w-]{3,100})(?:[/?#]|$)"), "LinkedIn"),
    (re.compile(r"tiktok\.com/@([\w.]{2,24})(?:[/?#]|$)"), "TikTok"),
    (re.compile(r"youtube\.com/@([\w-]{3,30})(?:[/?#]|$)"), "YouTube"),
    (re.compile(r"medium\.com/@([\w-]{3,50})(?:[/?#]|$)"), "Medium"),
    (re.compile(r"steamcommunity\.com/id/([\w-]{2,32})(?:[/?#]|$)"), "Steam"),
]

_SKIP_USERNAMES = frozenset({
    "share", "intent", "status", "photo", "video", "hashtag", "search",
    "explore", "login", "signup", "watch", "channel", "user", "profile",
    "settings", "help", "about", "home", "feed", "notifications", "messages",
})


def _make_identity(raw_value: str, method: ExtractionMethod) -> dict | None:
    """Convert a raw extracted value into an identity dict."""
    if not raw_value or len(raw_value) > 200:
        return None

    identity_type = method.identity_type
    value = raw_value.strip()
    hint_platform = method.hint_platform

    if identity_type == IdentityType.URL:
        parsed = _parse_profile_url(value)
        if parsed:
            value, hint_platform_from_url = parsed
            hint_platform = hint_platform or hint_platform_from_url
            identity_type = IdentityType.USERNAME
        else:
            return None

    return {
        "value": value,
        "type": identity_type.value,
        "hint_platform": hint_platform,
        "source": f"extraction rule ({method.type.value})",
    }


def _parse_profile_url(url: str) -> tuple[str, str] | None:
    for pattern, platform in _URL_PATTERNS:
        m = pattern.search(url)
        if m:
            username = m.group(1).lstrip("@")
            if username.lower() not in _SKIP_USERNAMES:
                return (username, platform)
    return None
