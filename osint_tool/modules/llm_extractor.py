"""LLM-powered extraction rule learning.

Sends cleaned profile-page HTML to Anthropic to identify linked identities
and learn reusable extraction rules (CSS selectors, XPath, regex) that get
cached for future visits without further LLM involvement.
"""
import json
import re
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.json"

_ANTHROPIC_IMPORT_ERROR = None
try:
    import anthropic as _anthropic_mod
except ImportError as _e:
    _anthropic_mod = None
    _ANTHROPIC_IMPORT_ERROR = (
        "anthropic package not found. "
        "Run: pip install anthropic>=0.25"
    )


def load_api_key() -> str | None:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text()).get("anthropic_api_key") or None
        except Exception:
            return None
    return None


def has_api_key() -> bool:
    return bool(load_api_key())


def _require_anthropic() -> None:
    if _anthropic_mod is None:
        raise ImportError(_ANTHROPIC_IMPORT_ERROR)


_EXTRACTION_PROMPT = """\
You are analyzing a cleaned HTML profile page from the domain "{domain}".

Your task:
1. Find all linked cross-platform usernames, profile URLs, and email addresses visible in this page.
2. For each identity found, provide extraction rules in as many formats as applicable:
   - CSS selector (with optional attribute to read)
   - XPath expression
   - Regex pattern (with capture group number)
3. Check if the page contains JSON-LD structured data (it will be provided separately if present). \
If so, provide the JSONPath to relevant identity fields.

Return your response as a JSON object with this exact schema:
{{
  "identities": [
    {{
      "value": "the_extracted_username_or_url",
      "type": "username" | "email" | "url",
      "hint_platform": "GitHub" | "Twitter/X" | "Instagram" | etc. | null
    }}
  ],
  "methods": [
    {{
      "type": "json_ld" | "css" | "xpath" | "regex",
      "identity_type": "url" | "username" | "email",
      "path": "$.sameAs[*]",
      "selector": "a.social-link",
      "attr": "href",
      "expr": "//a[@class='social']/@href",
      "pattern": "twitter\\\\.com/@?(\\\\w+)",
      "group": 1,
      "hint_platform": "Twitter/X"
    }}
  ]
}}

Rules:
- Only include identities you are confident about. Do not hallucinate.
- Methods should be general enough to work on OTHER users' profiles on the same site, not just this specific page.
- Prefer methods that target semantic HTML (classes, data attributes) over positional selectors.
- For regex, use Python regex syntax.
- Only include fields relevant to each method type (e.g. "selector"/"attr" for css, "expr" for xpath, etc.).
- Return ONLY the JSON object, no explanation or markdown fences.
{json_ld_section}

Here is the cleaned HTML:
```
{html}
```"""

MAX_HTML_CHARS = 30_000
MODEL = "claude-haiku-4-5-20251001"


async def llm_extract(domain: str, cleaned_html: str, json_ld_blocks: list[dict]) -> dict | None:
    """Call the LLM to extract identities and learn extraction rules.

    Returns dict with "identities" and "methods" keys, or None if no API key
    or extraction failed.
    """
    api_key = load_api_key()
    if not api_key:
        return None

    _require_anthropic()
    client = _anthropic_mod.AsyncAnthropic(api_key=api_key)

    if json_ld_blocks:
        ld_text = json.dumps(json_ld_blocks, indent=2)[:3000]
        json_ld_section = f"\nJSON-LD data found on this page:\n```json\n{ld_text}\n```"
    else:
        json_ld_section = "\nNo JSON-LD structured data was found on this page."

    html_for_prompt = cleaned_html[:MAX_HTML_CHARS]
    if len(cleaned_html) > MAX_HTML_CHARS:
        html_for_prompt += "\n... [truncated] ..."

    prompt = _EXTRACTION_PROMPT.format(
        domain=domain,
        html=html_for_prompt,
        json_ld_section=json_ld_section,
    )

    try:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

        result = json.loads(text)
        if not isinstance(result, dict):
            return None
        if "identities" not in result or "methods" not in result:
            return None
        return result
    except Exception:
        return None
