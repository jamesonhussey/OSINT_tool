import asyncio
import aiohttp

HEADERS = {
    "User-Agent": "osint-tool/1.0",
    "Accept": "application/vnd.github+json",
}

REPOS_PER_PAGE = 100   # GitHub maximum
EVENTS_PER_PAGE = 100  # GitHub maximum; API caps total history at ~300 events


async def _get(session: aiohttp.ClientSession, url: str):
    try:
        async with session.get(
            url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            if resp.status in (403, 429):
                return {"_rate_limited": True}
    except Exception:
        pass
    return None


def _parse_repos(data) -> list:
    if not isinstance(data, list):
        return []
    repos = []
    for r in data:
        repos.append({
            "name": r.get("name", ""),
            "description": r.get("description"),
            "stars": r.get("stargazers_count", 0),
            "language": r.get("language"),
            "url": r.get("html_url", ""),
            "updated_at": r.get("updated_at", ""),
            "fork": r.get("fork", False),
        })
    return repos


def _summarize_event(event_type: str, payload: dict) -> str | None:
    if event_type == "PushEvent":
        commits = payload.get("commits", [])
        n = len(commits)
        msg = commits[0].get("message", "").split("\n")[0] if commits else ""
        return f"Pushed {n} commit{'s' if n != 1 else ''}: {msg}"
    if event_type == "CreateEvent":
        ref_type = payload.get("ref_type", "")
        ref = payload.get("ref") or ""
        return f"Created {ref_type} {ref}".strip()
    if event_type == "DeleteEvent":
        return f"Deleted {payload.get('ref_type', '')}"
    if event_type == "WatchEvent":
        return "Starred the repository"
    if event_type == "ForkEvent":
        return "Forked the repository"
    if event_type == "IssuesEvent":
        action = payload.get("action", "")
        title = payload.get("issue", {}).get("title", "")
        return f"{action.capitalize()} issue: {title}"
    if event_type == "PullRequestEvent":
        action = payload.get("action", "")
        title = payload.get("pull_request", {}).get("title", "")
        return f"{action.capitalize()} PR: {title}"
    if event_type == "IssueCommentEvent":
        return "Commented on an issue"
    if event_type == "PullRequestReviewEvent":
        return "Reviewed a pull request"
    if event_type == "ReleaseEvent":
        tag = payload.get("release", {}).get("tag_name", "")
        return f"Published release {tag}"
    if event_type == "PublicEvent":
        return "Made repository public"
    if event_type == "MemberEvent":
        login = payload.get("member", {}).get("login", "")
        return f"Added {login} as collaborator"
    return None


def _parse_events(data) -> list:
    if not isinstance(data, list):
        return []
    events = []
    for e in data:
        event_type = e.get("type", "")
        repo_name = e.get("repo", {}).get("name", "")
        summary = _summarize_event(event_type, e.get("payload", {}))
        if summary:
            events.append({
                "type": event_type,
                "repo": repo_name,
                "repo_url": f"https://github.com/{repo_name}",
                "summary": summary,
                "created_at": e.get("created_at", ""),
            })
    return events


async def fetch_github_content(
    username: str,
    content_type: str | None = None,
    page: int = 1,
) -> dict:
    """
    Fetch GitHub repos and/or public events.

    - content_type=None    → initial load, returns both repos and events
    - content_type='repos'   → paginated repos only
    - content_type='events'  → paginated events only (GitHub caps at ~300 total)

    'has_more' signals whether another page likely exists.
    """
    async with aiohttp.ClientSession() as session:
        if content_type is None:
            repos_data, events_data = await asyncio.gather(
                _get(session, f"https://api.github.com/users/{username}/repos"
                              f"?sort=updated&per_page={REPOS_PER_PAGE}&page=1"),
                _get(session, f"https://api.github.com/users/{username}/events/public"
                              f"?per_page={EVENTS_PER_PAGE}&page=1"),
            )
            repos = _parse_repos(repos_data)
            events = _parse_events(events_data)
            return {
                "repos": {
                    "items": repos,
                    "has_more": len(repos) == REPOS_PER_PAGE,
                    "page": 1,
                },
                "events": {
                    "items": events,
                    "has_more": len(events) == EVENTS_PER_PAGE,
                    "page": 1,
                },
            }

        if content_type == "repos":
            data = await _get(
                session,
                f"https://api.github.com/users/{username}/repos"
                f"?sort=updated&per_page={REPOS_PER_PAGE}&page={page}",
            )
            if isinstance(data, dict) and data.get("_rate_limited"):
                return {"items": [], "has_more": False, "page": page, "rate_limited": True}
            items = _parse_repos(data)
            return {"items": items, "has_more": len(items) == REPOS_PER_PAGE, "page": page}

        if content_type == "events":
            data = await _get(
                session,
                f"https://api.github.com/users/{username}/events/public"
                f"?per_page={EVENTS_PER_PAGE}&page={page}",
            )
            if isinstance(data, dict) and data.get("_rate_limited"):
                return {"items": [], "has_more": False, "page": page, "rate_limited": True}
            items = _parse_events(data)
            return {"items": items, "has_more": len(items) == EVENTS_PER_PAGE, "page": page}

    return {}
