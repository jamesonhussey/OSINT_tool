import json
import re
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.json"


def load_api_key() -> str | None:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text()).get("anthropic_api_key") or None
        except Exception:
            return None
    return None


async def generate_aliases(input_str: str, context: str | None = None) -> dict:
    api_key = load_api_key()
    if api_key:
        try:
            return await _ai_aliases(input_str, context, api_key)
        except Exception:
            pass
    return _programmatic_aliases(input_str)


async def _ai_aliases(input_str: str, context: str | None, api_key: str) -> dict:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)

    context_line = f"\nContext: this was found on {context}." if context else ""
    prompt = f"""Analyze this email or username: "{input_str}"{context_line}

Return a JSON object with exactly these fields:
- "components": object with "first_name", "last_name" (empty string if not determinable), "numbers" (string, empty if none), "number_meaning" (e.g. "birth year", "random", "none")
- "username_variants": array of up to 12 likely usernames this person uses on other platforms (do not include the original input)
- "realname_variants": array of real-name search strings for Facebook/LinkedIn/Instagram (e.g. "First Last") — only include if names are determinable, otherwise empty array

Return only valid JSON, no explanation, no markdown fences."""

    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    text = re.sub(r"^```(?:json)?\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


def _programmatic_aliases(input_str: str) -> dict:
    from osint_tool.modules.email_utils import (
        extract_username_from_email,
        generate_username_variations,
    )

    is_email = "@" in input_str
    if is_email:
        variants = generate_username_variations(input_str)
        username = extract_username_from_email(input_str)
    else:
        variants = _basic_variants(input_str)
        username = input_str

    return {
        "components": {
            "first_name": "",
            "last_name": "",
            "numbers": "",
            "number_meaning": "none",
        },
        "username_variants": [v for v in variants if v.lower() != input_str.lower() and v.lower() != username.lower()],
        "realname_variants": [],
    }


def _basic_variants(username: str) -> list[str]:
    variants = set()
    stripped = re.sub(r"\d+$", "", username)
    if stripped and stripped != username:
        variants.add(stripped)
    for sep in [".", "-", "_", ""]:
        variants.add(re.sub(r"[.\-_]", sep, username))
    return sorted(v for v in variants if len(v) > 1)
