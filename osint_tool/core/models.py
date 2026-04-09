from dataclasses import dataclass, field
from enum import Enum


class Platform(Enum):
    GITHUB = "GitHub"
    TWITTER = "Twitter/X"
    INSTAGRAM = "Instagram"
    REDDIT = "Reddit"
    LINKEDIN = "LinkedIn"
    PINTEREST = "Pinterest"
    TIKTOK = "TikTok"
    YOUTUBE = "YouTube"
    STEAM = "Steam"
    MEDIUM = "Medium"
    GRAVATAR = "Gravatar"


class AccountStatus(Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    ERROR = "error"


@dataclass
class AccountResult:
    platform: Platform
    username: str
    url: str
    status: AccountStatus
    extra_info: dict = field(default_factory=dict)
    html_body: str | None = field(default=None, repr=False)


@dataclass
class GravatarProfile:
    email: str
    hash: str
    display_name: str | None = None
    profile_url: str | None = None
    avatar_url: str | None = None
    about: str | None = None
    location: str | None = None
    urls: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    query: str
    query_type: str  # "email" or "username"
    accounts: list[AccountResult] = field(default_factory=list)
    gravatar: GravatarProfile | None = None
    derived_usernames: list[str] = field(default_factory=list)

    @property
    def found_accounts(self) -> list[AccountResult]:
        return [a for a in self.accounts if a.status == AccountStatus.FOUND]
