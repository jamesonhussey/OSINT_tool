import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from osint_tool.core.config_loader import (
    CONFIG_PATH,
    api_key_source,
    get_anthropic_api_key,
    load_config_json,
    load_dotenv_once,
)
from osint_tool.core.engine import search
from osint_tool.core.models import AccountResult, GravatarProfile, SearchResult
from osint_tool.core.discovery import DiscoveryEngine

load_dotenv_once()
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

# Cooperative cancel: one Event per active SSE stream (keyed by client search_id).
_active_cancel_events: dict[str, asyncio.Event] = {}


def _save_config(data: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


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


@app.get("/api/settings")
async def get_settings():
    load_dotenv_once()
    effective = get_anthropic_api_key()
    key_src = api_key_source()
    config = load_config_json()
    preview = ""
    if effective:
        preview = f"...{effective[-4:]}" if len(effective) > 4 else ""
    return {
        "has_api_key": bool(effective),
        "api_key_preview": preview,
        "key_source": key_src,
        "auto_search_variants": config.get("auto_search_variants", False),
        "extraction_mode": "full" if effective else "basic",
    }


class SettingsUpdate(BaseModel):
    anthropic_api_key: str | None = None
    auto_search_variants: bool | None = None


@app.post("/api/settings")
async def update_settings(body: SettingsUpdate):
    config = load_config_json()
    if body.anthropic_api_key is not None:
        config["anthropic_api_key"] = body.anthropic_api_key
    if body.auto_search_variants is not None:
        config["auto_search_variants"] = body.auto_search_variants
    _save_config(config)
    return {"ok": True}


@app.post("/api/reset-extraction-cache")
async def reset_extraction_cache():
    """Remove local_rules.json so only bundled default_rules.json applies until the LLM learns again."""
    from osint_tool.data.rule_cache import reset_local_rules
    reset_local_rules()
    return {"ok": True, "message": "Local extraction cache cleared. Restart not required."}


class VariantsRequest(BaseModel):
    input: str
    context: str | None = None


@app.post("/api/generate-variants")
async def generate_variants(body: VariantsRequest):
    from osint_tool.modules.alias_gen import generate_aliases
    try:
        result = await generate_aliases(body.input, body.context)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class FlagIdentityRequest(BaseModel):
    domain: str
    identity_value: str
    reason: str | None = None


@app.post("/api/flag-identity")
async def flag_identity(body: FlagIdentityRequest):
    """Mark a domain's extraction rule for re-learning."""
    from osint_tool.data.rule_cache import get_rule_cache
    cache = get_rule_cache()
    cache.mark_needs_relearn(body.domain)
    return {"ok": True, "domain": body.domain}


class HybridsRequest(BaseModel):
    seeds: list[dict]


@app.post("/api/generate-hybrids")
async def generate_hybrids_endpoint(body: HybridsRequest):
    from osint_tool.modules.alias_gen import generate_hybrids
    try:
        result = await generate_hybrids(body.seeds)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CancelSearchRequest(BaseModel):
    search_id: str


@app.post("/api/search/cancel")
async def cancel_search(body: CancelSearchRequest):
    """Signal the discovery engine to stop after the current hop (cooperative)."""
    ev = _active_cancel_events.get(body.search_id)
    if ev is not None:
        ev.set()
    return {"ok": True}


@app.get("/api/search/stream")
async def search_stream(
    q: str = Query(..., min_length=1),
    cap: bool = Query(True),
    danger: bool = Query(
        False,
        description="If true, auto-queue discovered identities (multi-hop). Default is manual expand.",
    ),
    sid: str | None = Query(
        None,
        description="Client-generated id for POST /api/search/cancel cooperative stop.",
    ),
):
    """SSE endpoint for multi-hop streaming discovery."""
    cancel_event: asyncio.Event | None = None
    if sid:
        cancel_event = asyncio.Event()
        _active_cancel_events[sid] = cancel_event

    engine = DiscoveryEngine(
        q.strip(),
        hop_cap=100 if cap else None,
        auto_expand=danger,
        cancel_event=cancel_event,
    )

    async def event_gen():
        try:
            async for event_type, event_data in engine.run():
                yield f"event: {event_type}\ndata: {json.dumps(event_data)}\n\n"
        finally:
            if sid:
                _active_cancel_events.pop(sid, None)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
