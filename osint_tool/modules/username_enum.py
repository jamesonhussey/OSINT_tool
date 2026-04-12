import asyncio
from urllib.parse import quote

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


async def _check_gitlab(session: aiohttp.ClientSession, username: str) -> CheckResult:
    url = f"https://gitlab.com/api/v4/users?username={quote(username)}"
    async with session.get(
        url,
        headers={**HEADERS, "Accept": "application/json"},
        timeout=aiohttp.ClientTimeout(total=10),
    ) as resp:
        if resp.status != 200:
            st = AccountStatus.NOT_FOUND if resp.status == 404 else AccountStatus.ERROR
            return st, None
        try:
            data = await resp.json()
        except Exception:
            return AccountStatus.ERROR, None
        if isinstance(data, list) and len(data) > 0:
            return AccountStatus.FOUND, None
        return AccountStatus.NOT_FOUND, None


async def _check_codeberg(session: aiohttp.ClientSession, username: str) -> CheckResult:
    url = f"https://codeberg.org/api/v1/users/{username}"
    async with session.get(
        url,
        headers={**HEADERS, "Accept": "application/json"},
        timeout=aiohttp.ClientTimeout(total=10),
    ) as resp:
        if resp.status == 200:
            return AccountStatus.FOUND, None
        if resp.status == 404:
            return AccountStatus.NOT_FOUND, None
        return AccountStatus.ERROR, None


async def _check_docker_hub(session: aiohttp.ClientSession, username: str) -> CheckResult:
    url = f"https://hub.docker.com/v2/users/{username}/"
    async with session.get(
        url,
        headers={**HEADERS, "Accept": "application/json"},
        timeout=aiohttp.ClientTimeout(total=10),
    ) as resp:
        if resp.status == 200:
            return AccountStatus.FOUND, None
        if resp.status == 404:
            return AccountStatus.NOT_FOUND, None
        return AccountStatus.ERROR, None


async def _check_devto(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_status(session, f"https://dev.to/{username}")


async def _check_vimeo(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_status(session, f"https://vimeo.com/{username}")


async def _check_soundcloud(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_body(
        session,
        f"https://soundcloud.com/{username}",
        ["sorry, we couldn't find that sound", "not found", "page not found"],
    )


async def _check_patreon(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_body(
        session,
        f"https://www.patreon.com/{username}",
        ["no matching creator", "page not found", "doesn't exist"],
    )


async def _check_product_hunt(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_body(
        session,
        f"https://www.producthunt.com/@{username}",
        ["page not found", "doesn't exist", "no users"],
    )


async def _check_behance(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_body(
        session,
        f"https://www.behance.net/{username}",
        ["project not found", "page not found", "can't be found"],
    )


async def _check_dribbble(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_body(
        session,
        f"https://dribbble.com/{username}",
        ["page not found", "no results", "nothing here"],
    )


async def _check_flickr(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_body(
        session,
        f"https://www.flickr.com/people/{username}/",
        ["page not found", "not found", "does not exist"],
    )


async def _check_keybase(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_status(session, f"https://keybase.io/{username}")


async def _check_huggingface(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_status(session, f"https://huggingface.co/{username}")


async def _check_npm(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_status(session, f"https://www.npmjs.com/~{username}")


async def _check_kickstarter(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_body(
        session,
        f"https://www.kickstarter.com/profile/{username}",
        ["page not found", "we can't find", "doesn't exist"],
    )


async def _check_leetcode(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_body(
        session,
        f"https://leetcode.com/{username}/",
        ["page not found", "user not found", "does not exist"],
    )


async def _check_chess_com(session: aiohttp.ClientSession, username: str) -> CheckResult:
    return await _check_by_body(
        session,
        f"https://www.chess.com/member/{username}",
        ["page not found", "member not found", "could not be found"],
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
    (Platform.GITLAB, _check_gitlab, "https://gitlab.com/{username}"),
    (Platform.DEVTO, _check_devto, "https://dev.to/{username}"),
    (Platform.VIMEO, _check_vimeo, "https://vimeo.com/{username}"),
    (Platform.SOUNDCLOUD, _check_soundcloud, "https://soundcloud.com/{username}"),
    (Platform.PATREON, _check_patreon, "https://www.patreon.com/{username}"),
    (Platform.PRODUCT_HUNT, _check_product_hunt, "https://www.producthunt.com/@{username}"),
    (Platform.BEHANCE, _check_behance, "https://www.behance.net/{username}"),
    (Platform.DRIBBBLE, _check_dribbble, "https://dribbble.com/{username}"),
    (Platform.FLICKR, _check_flickr, "https://www.flickr.com/people/{username}/"),
    (Platform.KEYBASE, _check_keybase, "https://keybase.io/{username}"),
    (Platform.HUGGINGFACE, _check_huggingface, "https://huggingface.co/{username}"),
    (Platform.DOCKER_HUB, _check_docker_hub, "https://hub.docker.com/u/{username}"),
    (Platform.NPM, _check_npm, "https://www.npmjs.com/~{username}"),
    (Platform.KICKSTARTER, _check_kickstarter, "https://www.kickstarter.com/profile/{username}"),
    (Platform.CODEBERG, _check_codeberg, "https://codeberg.org/{username}"),
    (Platform.LEETCODE, _check_leetcode, "https://leetcode.com/{username}/"),
    (Platform.CHESS_COM, _check_chess_com, "https://www.chess.com/member/{username}"),
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
