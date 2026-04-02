import hashlib
import aiohttp
from osint_tool.core.models import GravatarProfile


def email_to_gravatar_hash(email: str) -> str:
    return hashlib.md5(email.strip().lower().encode()).hexdigest()


async def lookup_gravatar(email: str) -> GravatarProfile | None:
    """Look up a Gravatar profile by email address."""
    email_hash = email_to_gravatar_hash(email)
    profile_url = f"https://gravatar.com/{email_hash}.json"
    avatar_url = f"https://gravatar.com/avatar/{email_hash}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                profile_url,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json()
                entry = data.get("entry", [{}])[0]

                urls = [
                    u.get("value", "")
                    for u in entry.get("urls", [])
                    if u.get("value")
                ]

                return GravatarProfile(
                    email=email,
                    hash=email_hash,
                    display_name=entry.get("displayName"),
                    profile_url=f"https://gravatar.com/{email_hash}",
                    avatar_url=avatar_url,
                    about=entry.get("aboutMe"),
                    location=entry.get("currentLocation"),
                    urls=urls,
                )
    except (aiohttp.ClientError, Exception):
        return None
