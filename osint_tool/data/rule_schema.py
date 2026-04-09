"""Data models for extraction rules.

Each rule describes how to extract linked identities from a specific
domain's profile pages, with multiple extraction methods tried in
priority order.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class MethodType(Enum):
    JSON_LD = "json_ld"
    CSS = "css"
    XPATH = "xpath"
    REGEX = "regex"


class IdentityType(Enum):
    URL = "url"
    USERNAME = "username"
    EMAIL = "email"


@dataclass
class ExtractionMethod:
    type: MethodType
    identity_type: IdentityType
    path: str | None = None           # json_ld: JSONPath into LD block
    selector: str | None = None       # css: CSS selector
    attr: str | None = None           # css: attribute to read (None = text)
    expr: str | None = None           # xpath: XPath expression
    pattern: str | None = None        # regex: pattern string
    group: int = 1                    # regex: capture group number
    hint_platform: str | None = None  # optional platform hint

    def to_dict(self) -> dict:
        d: dict = {"type": self.type.value, "identity_type": self.identity_type.value}
        for key in ("path", "selector", "attr", "expr", "pattern", "hint_platform"):
            val = getattr(self, key)
            if val is not None:
                d[key] = val
        if self.type == MethodType.REGEX:
            d["group"] = self.group
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ExtractionMethod:
        return cls(
            type=MethodType(d["type"]),
            identity_type=IdentityType(d["identity_type"]),
            path=d.get("path"),
            selector=d.get("selector"),
            attr=d.get("attr"),
            expr=d.get("expr"),
            pattern=d.get("pattern"),
            group=d.get("group", 1),
            hint_platform=d.get("hint_platform"),
        )


@dataclass
class SiteRule:
    domain: str
    version: int = 1
    updated_at: str = ""
    fingerprint: str = ""
    methods: list[ExtractionMethod] = field(default_factory=list)
    skip: bool = False
    skip_reason: str | None = None
    needs_relearn: bool = False
    fail_count: int = 0

    def to_dict(self) -> dict:
        d: dict = {
            "domain": self.domain,
            "version": self.version,
            "updated_at": self.updated_at or datetime.now(timezone.utc).isoformat(),
            "fingerprint": self.fingerprint,
            "methods": [m.to_dict() for m in self.methods],
            "skip": self.skip,
        }
        if self.skip_reason:
            d["skip_reason"] = self.skip_reason
        if self.needs_relearn:
            d["needs_relearn"] = True
        if self.fail_count > 0:
            d["fail_count"] = self.fail_count
        return d

    @classmethod
    def from_dict(cls, d: dict) -> SiteRule:
        return cls(
            domain=d["domain"],
            version=d.get("version", 1),
            updated_at=d.get("updated_at", ""),
            fingerprint=d.get("fingerprint", ""),
            methods=[ExtractionMethod.from_dict(m) for m in d.get("methods", [])],
            skip=d.get("skip", False),
            skip_reason=d.get("skip_reason"),
            needs_relearn=d.get("needs_relearn", False),
            fail_count=d.get("fail_count", 0),
        )
