import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from osint_tool.core.engine import search
from osint_tool.core.models import AccountResult, GravatarProfile, SearchResult
from osint_tool.core.discovery import DiscoveryEngine
from osint_tool.modules.reddit import fetch_reddit_content
from osint_tool.modules.github import fetch_github_content
from osint_tool.modules.wayback import lookup_wayback

CONTENT_FETCHERS = {
    "reddit": fetch_reddit_content,
    "github": fetch_github_content,
}

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="OSINT Tool")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _serialize_result(result: SearchResult) -> dict:
    """Convert SearchResult dataclass (with enums) to a plain dict for JSON."""

    def serialize_account(acc: AccountResult) -> dict:
        return {
            "platform": acc.platform.value,
            "username": acc.username,
            "url": acc.url,
            "status": acc.status.value,
        }

    def serialize_gravatar(g: GravatarProfile) -> dict:
        return {
            "display_name": g.display_name,
            "profile_url": g.profile_url,
            "avatar_url": g.avatar_url,
            "about": g.about,
            "location": g.location,
            "urls": g.urls,
        }

    return {
        "query": result.query,
        "query_type": result.query_type,
        "derived_usernames": result.derived_usernames,
        "gravatar": serialize_gravatar(result.gravatar) if result.gravatar else None,
        "accounts": [serialize_account(a) for a in result.accounts],
    }


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/search")
async def api_search(q: str = Query(..., min_length=1)):
    try:
        result = await search(q)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return _serialize_result(result)


@app.get("/api/content")
async def api_content(
    platform: str = Query(...),
    username: str = Query(..., min_length=1),
    # content_type: 'posts'|'comments' (Reddit) or 'repos'|'events' (GitHub)
    # Omit for the initial load which returns all tabs at once.
    type: str = Query(None),
    # Reddit cursor-based pagination
    after: str = Query(None),
    # GitHub page-based pagination
    page: int = Query(1, ge=1),
):
    key = platform.lower()
    if key not in CONTENT_FETCHERS:
        raise HTTPException(status_code=400, detail=f"Unsupported platform: {platform}")
    try:
        if key == "reddit":
            return await fetch_reddit_content(username, content_type=type, after=after)
        else:
            return await fetch_github_content(username, content_type=type, page=page)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/wayback")
async def api_wayback(url: str = Query(..., min_length=1)):
    try:
        return await lookup_wayback(url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/search/stream")
async def search_stream(
    q: str = Query(..., min_length=1),
    cap: bool = Query(True),
):
    """SSE endpoint for multi-hop streaming discovery."""
    engine = DiscoveryEngine(q, hop_cap=100 if cap else None)

    async def event_gen():
        async for event_type, event_data in engine.run():
            yield f"event: {event_type}\ndata: {json.dumps(event_data)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
