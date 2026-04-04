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


async def generate_hybrids(seeds: list[dict]) -> dict:
    """Generate hybrid username combinations from multiple known seeds."""
    api_key = load_api_key()
    if not api_key:
        return {
            "analysis": "No API key configured — set one in Settings to use hybrid generation.",
            "username_variants": [],
            "realname_variants": [],
        }
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)
    seed_lines = "\n".join(f'- "{s["value"]}" ({s["type"]})' for s in seeds)

    prompt = f"""These emails and usernames all belong to the same person:
{seed_lines}

Analyze patterns across all of them: extract name components, identify recurring numbers or words, note how they vary their style across platforms (separators, capitalisation, number placement).

Then generate 15-20 new username combinations that:
1. Mix elements from different seeds (e.g. base from one + numbers from another)
2. Try adjacent numbers (±1, ±2) from any numbers found
3. Apply separator variations (_, ., -) to combined forms
4. If real names are determinable, include real-name search strings for Facebook/LinkedIn

Return JSON with exactly these fields:
{{
  "analysis": "one sentence describing the patterns you found",
  "username_variants": [...],
  "realname_variants": [...]
}}

Return only valid JSON, no explanation, no markdown fences."""

    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=768,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    text = re.sub(r"^```(?:json)?\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


async def _ai_aliases(input_str: str, context: str | None, api_key: str) -> dict:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)

    context_line = f"\nContext: this was found on {context}." if context else ""
    prompt = f"""Analyze this email or username and generate creative username variations: "{input_str}"{context_line}

Generate variations using these strategies:
1. If numbers are present: try ±1, ±2 adjacent numbers; the full 4-digit year if a 2-digit year is likely (e.g. 99 → 1999); no numbers at all
2. Separator variations: with underscores, dots, hyphens, no separator between name parts
3. If this looks like a real name (e.g. firstlast, john.doe, jsmith): decompose into parts and try firstname, lastname, f.lastname, first.last, flast, lastfirst, last_first, etc.
4. Common suffix/prefix patterns: _, x, its, real, official, _official, the
5. Capitalisation variants if relevant (e.g. FirstLast, FIRSTLAST)

Return JSON with exactly these fields:
{{
  "components": {{"first_name": "", "last_name": "", "numbers": "", "number_meaning": ""}},
  "username_variants": [10-15 distinct variations, NOT including the original input],
  "realname_variants": ["First Last" style strings for Facebook/LinkedIn — only if names are determinable, else empty array]
}}

Return only valid JSON, no explanation, no markdown fences."""

    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=640,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    text = re.sub(r"^```(?:json)?\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


def _programmatic_aliases(input_str: str) -> dict:
    from osint_tool.modules.email_utils import extract_username_from_email

    is_email = "@" in input_str
    username = extract_username_from_email(input_str) if is_email else input_str

    variants: set[str] = set()

    # Strip trailing numbers
    stripped = re.sub(r"\d+$", "", username)
    if stripped and stripped != username:
        variants.add(stripped)

    # Separator swaps
    for sep in [".", "_", "-", ""]:
        variants.add(re.sub(r"[.\-_]", sep, username))

    # Adjacent number variants
    m = re.search(r"\d+$", username)
    if m:
        n = int(m.group())
        base = username[: m.start()]
        for delta in [-2, -1, 1, 2]:
            variants.add(f"{base}{n + delta}")
        # 2-digit year → full year
        if 0 <= n <= 99:
            variants.add(f"{base}{1900 + n}")
            variants.add(f"{base}{2000 + n}")

    result = sorted(
        v for v in variants if len(v) > 1 and v.lower() != input_str.lower() and v.lower() != username.lower()
    )
    return {
        "components": {"first_name": "", "last_name": "", "numbers": "", "number_meaning": "none"},
        "username_variants": result,
        "realname_variants": [],
    }
