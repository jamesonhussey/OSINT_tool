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

CheckResult = tuple[AccountStatus, str | None]


async def _check_by_status(
    session: aiohttp.ClientSession, url: str
) -> CheckResult:
    """Simple check: 200 = found, anything else = not found."""
    async with session.get(
        url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10),
        allow_redirects=True,
    ) as resp:
        if resp.status == 200:
            body = await resp.text()
            return AccountStatus.FOUND, body
        return AccountStatus.NOT_FOUND, None


async def _check_by_body(
    session: aiohttp.ClientSession, url: str, not_found_indicators: list[str]
) -> CheckResult:
    """Check response body for not-found indicators. 200 + no indicators = found."""
    async with session.get(
        url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10),
        allow_redirects=True,
    ) as resp:
        if resp.status != 200:
            return AccountStatus.NOT_FOUND, None
        body = await resp.text()
        body_lower = body.lower()
        for indicator in not_found_indicators:
            if indicator in body_lower:
                return AccountStatus.NOT_FOUND, None
        return AccountStatus.FOUND, body


async def _check_github(session: aiohttp.ClientSession, username: str) -> CheckResult:
    url = f"https://api.github.com/users/{username}"
    async with session.get(
        url,
        headers={**HEADERS, "Accept": "application/vnd.github+json"},
        timeout=aiohttp.ClientTimeout(total=10),
    ) as resp:
        if resp.status == 200:
            return AccountStatus.FOUND, None  # API-based, no HTML
        elif resp.status == 404:
            return AccountStatus.NOT_FOUND, None
        else:
            return AccountStatus.ERROR, None


async def _check_instagram(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_body(
        session,
        f"https://www.instagram.com/{username}/",
        ["page not found", "this page isn't available", "unavailable"],
    )


async def _check_reddit(session: aiohttp.ClientSession, username: str) -> CheckResult:
    url = f"https://www.reddit.com/user/{username}/about.json"
    async with session.get(
        url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10),
    ) as resp:
        if resp.status != 200:
            return AccountStatus.NOT_FOUND, None
        data = await resp.json()
        if data.get("data", {}).get("is_suspended"):
            return AccountStatus.NOT_FOUND, None
        return AccountStatus.FOUND, None  # JSON API, no HTML


async def _check_pinterest(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_body(
        session,
        f"https://www.pinterest.com/{username}/",
        ["not found", "page not found"],
    )


async def _check_tiktok(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_body(
        session,
        f"https://www.tiktok.com/@{username}",
        ["not found", "sorry", "couldn't find this account", "unavailable"],
    )


async def _check_youtube(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_status(session, f"https://www.youtube.com/@{username}")


async def _check_steam(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_body(
        session,
        f"https://steamcommunity.com/id/{username}",
        ["the specified profile could not be found"],
    )


async def _check_medium(session: aiohttp.ClientSession, username: str) -> CheckResult:
    url = f"https://medium.com/@{username}"
    async with session.get(
        url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10),
        allow_redirects=True,
    ) as resp:
        if resp.status == 200:
            body = await resp.text()
            return AccountStatus.FOUND, body
        elif resp.status == 404:
            return AccountStatus.NOT_FOUND, None
        else:
            return AccountStatus.ERROR, None


async def _check_twitter(session: aiohttp.ClientSession, username: str) -> CheckResult:
    url = f"https://x.com/{username}"
    async with session.get(
        url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10),
        allow_redirects=True,
    ) as resp:
        if resp.status == 200:
            body = await resp.text()
            return AccountStatus.FOUND, body
        elif resp.status == 404:
            return AccountStatus.NOT_FOUND, None
        else:
            return AccountStatus.ERROR, None


async def _check_linkedin(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_body(
        session,
        f"https://www.linkedin.com/in/{username}/",
        ["page not found", "this page doesn't exist", "profile not found"],
    )


PLATFORM_CHECKS = [
    (Platform.GITHUB, _check_github, "https://github.com/{username}"),
    (Platform.TWITTER, _check_twitter, "https://x.com/{username}"),
    (Platform.INSTAGRAM, _check_instagram, "https://www.instagram.com/{username}/"),
    (Platform.REDDIT, _check_reddit, "https://www.reddit.com/user/{username}"),
    (Platform.LINKEDIN, _check_linkedin, "https://www.linkedin.com/in/{username}/"),
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
        status, html_body = await checker(session, username)
        return AccountResult(
            platform=platform, username=username, url=url,
            status=status, html_body=html_body,
        )
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
