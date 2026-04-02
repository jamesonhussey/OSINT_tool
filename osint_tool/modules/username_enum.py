import asyncio
import aiohttp
from osint_tool.core.models import AccountResult, AccountStatus, Platform


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


async def _check_by_status(
    session: aiohttp.ClientSession, url: str
) -> AccountStatus:
    """Simple check: 200 = found, anything else = not found."""
    async with session.get(
        url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10),
        allow_redirects=True,
    ) as resp:
        return AccountStatus.FOUND if resp.status == 200 else AccountStatus.NOT_FOUND


async def _check_by_body(
    session: aiohttp.ClientSession, url: str, not_found_indicators: list[str]
) -> AccountStatus:
    """Check response body for not-found indicators. 200 + no indicators = found."""
    async with session.get(
        url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10),
        allow_redirects=True,
    ) as resp:
        if resp.status != 200:
            return AccountStatus.NOT_FOUND
        body = (await resp.text()).lower()
        for indicator in not_found_indicators:
            if indicator in body:
                return AccountStatus.NOT_FOUND
        return AccountStatus.FOUND


async def _check_github(session: aiohttp.ClientSession, username: str) -> AccountStatus:
    # GitHub returns 404 for non-existent users
    return await _check_by_status(session, f"https://github.com/{username}")


async def _check_instagram(session: aiohttp.ClientSession, username: str) -> AccountStatus:
    # Instagram returns 200 but body contains "Page Not Found" for missing users
    return await _check_by_body(
        session,
        f"https://www.instagram.com/{username}/",
        ["page not found", "this page isn't available", "unavailable"],
    )


async def _check_reddit(session: aiohttp.ClientSession, username: str) -> AccountStatus:
    # Reddit's JSON about endpoint returns 200 for real users, non-200 for fake
    url = f"https://www.reddit.com/user/{username}/about.json"
    async with session.get(
        url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10),
    ) as resp:
        if resp.status != 200:
            return AccountStatus.NOT_FOUND
        data = await resp.json()
        # Suspended/shadowbanned accounts have "is_suspended": true
        if data.get("data", {}).get("is_suspended"):
            return AccountStatus.NOT_FOUND
        return AccountStatus.FOUND


async def _check_pinterest(session: aiohttp.ClientSession, username: str) -> AccountStatus:
    return await _check_by_body(
        session,
        f"https://www.pinterest.com/{username}/",
        ["not found", "page not found"],
    )


async def _check_tiktok(session: aiohttp.ClientSession, username: str) -> AccountStatus:
    return await _check_by_body(
        session,
        f"https://www.tiktok.com/@{username}",
        ["not found", "sorry", "couldn't find this account", "unavailable"],
    )


async def _check_youtube(session: aiohttp.ClientSession, username: str) -> AccountStatus:
    # YouTube returns 404 for non-existent channels
    return await _check_by_status(session, f"https://www.youtube.com/@{username}")


async def _check_steam(session: aiohttp.ClientSession, username: str) -> AccountStatus:
    # Steam returns 200 for both, but body contains error text for missing profiles
    return await _check_by_body(
        session,
        f"https://steamcommunity.com/id/{username}",
        ["the specified profile could not be found"],
    )


async def _check_medium(session: aiohttp.ClientSession, username: str) -> AccountStatus:
    # Medium blocks most automated requests with 403; treat as unreliable
    url = f"https://medium.com/@{username}"
    async with session.get(
        url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10),
        allow_redirects=True,
    ) as resp:
        if resp.status == 200:
            return AccountStatus.FOUND
        elif resp.status == 404:
            return AccountStatus.NOT_FOUND
        else:
            # 403 or other — can't determine
            return AccountStatus.ERROR


async def _check_twitter(session: aiohttp.ClientSession, username: str) -> AccountStatus:
    # Twitter/X aggressively blocks automated requests
    url = f"https://x.com/{username}"
    async with session.get(
        url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10),
        allow_redirects=True,
    ) as resp:
        if resp.status == 200:
            return AccountStatus.FOUND
        elif resp.status == 404:
            return AccountStatus.NOT_FOUND
        else:
            return AccountStatus.ERROR


# Maps Platform -> (checker function, profile URL template)
PLATFORM_CHECKS = [
    (Platform.GITHUB, _check_github, "https://github.com/{username}"),
    (Platform.TWITTER, _check_twitter, "https://x.com/{username}"),
    (Platform.INSTAGRAM, _check_instagram, "https://www.instagram.com/{username}/"),
    (Platform.REDDIT, _check_reddit, "https://www.reddit.com/user/{username}"),
    (Platform.PINTEREST, _check_pinterest, "https://www.pinterest.com/{username}/"),
    (Platform.TIKTOK, _check_tiktok, "https://www.tiktok.com/@{username}"),
    (Platform.YOUTUBE, _check_youtube, "https://www.youtube.com/@{username}"),
    (Platform.STEAM, _check_steam, "https://steamcommunity.com/id/{username}"),
    (Platform.MEDIUM, _check_medium, "https://medium.com/@{username}"),
]


async def _check_one(
    session: aiohttp.ClientSession,
    platform: Platform,
    checker,
    url_template: str,
    username: str,
) -> AccountResult:
    url = url_template.format(username=username)
    try:
        status = await checker(session, username)
        return AccountResult(platform=platform, username=username, url=url, status=status)
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return AccountResult(
            platform=platform, username=username, url=url, status=AccountStatus.ERROR,
        )


async def enumerate_username(username: str) -> list[AccountResult]:
    """Check if a username exists across all configured platforms."""
    async with aiohttp.ClientSession() as session:
        tasks = [
            _check_one(session, platform, checker, url_template, username)
            for platform, checker, url_template in PLATFORM_CHECKS
        ]
        results = await asyncio.gather(*tasks)
    return list(results)
