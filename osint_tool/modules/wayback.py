"""
Wayback Machine CDX API lookup.

Given a URL, queries the Internet Archive's CDX index and returns a summary
of the URL's archive history: when it was first/last seen, its HTTP status
code history, whether it appears to have been deleted, and a link to the
best available snapshot.

CDX API docs: https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server
"""
import asyncio
import aiohttp

CDX_API = "https://web.archive.org/cdx/search/cdx"
HEADERS = {"User-Agent": "osint-tool/1.0 (research)"}


async def _cdx(
    session: aiohttp.ClientSession,
    url: str,
    **params,
) -> list[list[str]]:
    try:
        async with session.get(
            CDX_API,
            params={"url": url, "output": "json", **params},
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            if not data or len(data) <= 1:
                return []
            return data[1:]  # skip the field-names header row
    except Exception:
        return []


def _ts_to_date(ts: str) -> str:
    """Convert CDX timestamp '20190314152012' → '2019-03-14'."""
    if len(ts) >= 8:
        return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
    return ts


async def lookup_wayback(url: str) -> dict:
    """
    Return an archive summary for a URL.

    Always returns a dict. Key 'archived' is False if the URL has never
    been indexed by the Wayback Machine, True otherwise.

    When archived=True the dict also contains:
        first_seen      ISO date of earliest snapshot
        last_seen       ISO date of most recent snapshot
        snapshot_count  Approximate number of snapshots (collapsed monthly)
        had_200         Whether the URL ever returned HTTP 200
        last_status     Most recent HTTP status code seen
        possibly_deleted  True if URL had 200s but recent status is 404/301/403
        snapshot_url    Direct link to the best (most recent 200) snapshot
        timeline        List of {"date", "status"} dicts showing status changes
    """
    async with aiohttp.ClientSession() as session:
        history, recent = await asyncio.gather(
            # Monthly-collapsed overview — gives first/last and rough count
            _cdx(
                session, url,
                fl="timestamp,statuscode",
                collapse="timestamp:6",
                limit=200,
            ),
            # 5 most recent snapshots — accurate current status
            _cdx(
                session, url,
                fl="timestamp,statuscode",
                limit=5,
                reverse="true",
            ),
        )

    if not history:
        return {"archived": False}

    statuses = [row[1] for row in history]
    had_200 = "200" in statuses
    last_status = recent[0][1] if recent else history[-1][1]
    possibly_deleted = had_200 and last_status in ("404", "301", "302", "403")

    # Build a compact timeline showing only status-code transitions
    timeline: list[dict] = []
    prev = None
    for ts, code in history:
        if code != prev:
            timeline.append({"date": _ts_to_date(ts), "status": code})
            prev = code

    # Best snapshot: most recent HTTP 200
    snapshot_url: str | None = None
    for ts, code in (recent or []):
        if code == "200":
            snapshot_url = f"https://web.archive.org/web/{ts}/{url}"
            break
    if not snapshot_url:
        for ts, code in reversed(history):
            if code == "200":
                snapshot_url = f"https://web.archive.org/web/{ts}/{url}"
                break

    last_ts = recent[0][0] if recent else history[-1][0]

    return {
        "archived": True,
        "first_seen": _ts_to_date(history[0][0]),
        "last_seen": _ts_to_date(last_ts),
        "snapshot_count": len(history),  # approx — collapsed to ~1/month
        "had_200": had_200,
        "last_status": last_status,
        "possibly_deleted": possibly_deleted,
        "snapshot_url": snapshot_url,
        "timeline": timeline[:15],
    }
