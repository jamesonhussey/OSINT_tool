"""HTML cleaner for profile page extraction.

Strips non-content elements (scripts, styles, nav, footer, comments),
extracts JSON-LD structured data before stripping, and collapses whitespace
to reduce token cost when sending to the LLM.
"""
import hashlib
import json
import re

from bs4 import BeautifulSoup, Comment


def clean_html(raw_html: str) -> tuple[str, list[dict], str]:
    """Clean raw HTML for extraction.

    Returns:
        (cleaned_html, json_ld_blocks, structural_fingerprint)
    """
    soup = BeautifulSoup(raw_html, "lxml")

    json_ld_blocks = _extract_json_ld(soup)

    for tag_name in ("script", "style", "nav", "footer", "noscript", "iframe", "svg"):
        for el in soup.find_all(tag_name):
            el.decompose()

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    for el in soup.find_all(attrs={"hidden": True}):
        el.decompose()
    for el in soup.find_all(attrs={"aria-hidden": "true"}):
        el.decompose()

    fingerprint = _compute_fingerprint(soup)

    cleaned = soup.prettify()
    cleaned = re.sub(r"\n\s*\n", "\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)

    return cleaned, json_ld_blocks, fingerprint


def _extract_json_ld(soup: BeautifulSoup) -> list[dict]:
    """Extract all JSON-LD script blocks."""
    blocks: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                blocks.append(data)
            elif isinstance(data, list):
                blocks.extend(d for d in data if isinstance(d, dict))
        except (json.JSONDecodeError, TypeError):
            continue
    return blocks


def _compute_fingerprint(soup: BeautifulSoup) -> str:
    """Hash the tag/class skeleton of the page for change detection."""
    parts: list[str] = []
    for el in soup.find_all(True):
        classes = el.get("class", [])
        class_str = ".".join(sorted(classes)) if classes else ""
        parts.append(f"{el.name}{'.' + class_str if class_str else ''}")
    skeleton = "|".join(parts)
    return hashlib.sha256(skeleton.encode()).hexdigest()[:16]
