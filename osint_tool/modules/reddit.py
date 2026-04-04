import asyncio
import aiohttp

# Reddit asks for a descriptive User-Agent with contact info for API access.
HEADERS = {"User-Agent": "osint-tool/1.0 (research; contact via GitHub)"}
BASE = "https://www.reddit.com/user"
MAX_LIMIT = 100  # Reddit's per-request maximum


async def _get(session: aiohttp.ClientSession, url: str):
    try:
        async with session.get(
            url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            if resp.status == 429:
                return {"_rate_limited": True}
    except Exception:
        pass
    return None


def _parse_posts(data: dict | None) -> tuple[list, str | None]:
    if not data:
        return [], None
    listing = data.get("data", {})
    items = []
    for child in listing.get("children", []):
        d = child.get("data", {})
        items.append({
            "title": d.get("title", ""),
            "subreddit": d.get("subreddit_name_prefixed", ""),
            "url": "https://reddit.com" + d.get("permalink", ""),
            "score": d.get("score", 0),
            "created_utc": d.get("created_utc", 0),
        })
    return items, listing.get("after")


def _parse_comments(data: dict | None) -> tuple[list, str | None]:
    if not data:
        return [], None
    listing = data.get("data", {})
    items = []
    for child in listing.get("children", []):
        d = child.get("data", {})
        body = d.get("body", "")
        items.append({
            "subreddit": d.get("subreddit_name_prefixed", ""),
            "body": body[:300] + ("…" if len(body) > 300 else ""),
            "url": "https://reddit.com" + d.get("permalink", ""),
            "score": d.get("score", 0),
            "created_utc": d.get("created_utc", 0),
        })
    return items, listing.get("after")


def _build_url(username: str, kind: str, after: str | None) -> str:
    url = f"{BASE}/{username}/{kind}.json?limit={MAX_LIMIT}&raw_json=1"
    if after:
        url += f"&after={after}"
    return url


async def fetch_reddit_content(
    username: str,
    content_type: str | None = None,
    after: str | None = None,
) -> dict:
    """
    Fetch Reddit posts and/or comments.

    - content_type=None  → initial load, returns both posts and comments
    - content_type='posts'    → paginated posts only
    - content_type='comments' → paginated comments only

    Each response includes an 'after' cursor (None when exhausted).
    """
    async with aiohttp.ClientSession() as session:
        if content_type is None:
            posts_data, comments_data = await asyncio.gather(
                _get(session, _build_url(username, "submitted", None)),
                _get(session, _build_url(username, "comments", None)),
            )
            posts, posts_after = _parse_posts(posts_data)
            comments, comments_after = _parse_comments(comments_data)
            return {
                "posts": {"items": posts, "after": posts_after},
                "comments": {"items": comments, "after": comments_after},
            }

        if content_type == "posts":
            data = await _get(session, _build_url(username, "submitted", after))
            if data and data.get("_rate_limited"):
                return {"items": [], "after": None, "rate_limited": True}
            items, next_after = _parse_posts(data)
            return {"items": items, "after": next_after}

        if content_type == "comments":
            data = await _get(session, _build_url(username, "comments", after))
            if data and data.get("_rate_limited"):
                return {"items": [], "after": None, "rate_limited": True}
            items, next_after = _parse_comments(data)
            return {"items": items, "after": next_after}

    return {}
