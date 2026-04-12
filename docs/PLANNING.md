# Planning & backlog

Miscellaneous follow-ups that are not part of day-to-day feature work. **Do not treat this as exhaustive**—add items as they come up.

## Security hardening (deferred)

Tackle before treating this tool as shared, network-exposed, or production-ready.

- **Secrets & configuration** (partially addressed)
  - **Done:** `ANTHROPIC_API_KEY` env var (and optional `.env` via `python-dotenv`) takes precedence over `config.json` for runtime API calls; see `.env.example` and `osint_tool/core/config_loader.py`. Settings UI still reads/writes `config.json`; GET `/api/settings` reports `key_source` (`environment` | `file` | `none`) so the UI can show when env overrides the file.
  - Prefer env or a secrets manager for deployment; keep `config.json` gitignored; rotate any key that has ever leaked.
  - Review what the web UI exposes under `/api/settings` (key previews, etc.) and tighten if the server is not strictly local.

- **Web surface**
  - If the app is bound beyond `127.0.0.1`, add authentication or network controls; review CORS and default bind behavior.
  - Consider rate limiting and payload limits on search and streaming endpoints to reduce abuse.

- **Dependencies & supply chain**
  - Periodically audit pinned versions (`requirements.txt`) and run a vulnerability scan appropriate for the deployment context.

- **Operational hygiene**
  - Document a minimal threat model (who runs the tool, what data flows where) when hardening work actually starts.

---

## Display names & broader identity extraction (deferred)

The LLM extraction system currently focuses on **cross-platform usernames and profile URLs**. A natural expansion is to also extract:

- **Display names / real names** — many platforms show a separate display name that may be the person's real name or a commonly used alias (e.g. GitHub's "Name" field, Twitter's display name).
- **Bio text** — bios often contain phrases like "also on Twitter as @..." or list personal websites.
- **Linked URLs** — personal sites, portfolios, Linktree-style link pages that may contain further social links.
- **"Also known as" references** — some platforms show previous usernames or alternative handles.

### Why it's deferred

This changes the data model (`SearchResult`, `AccountResult`) and the UI rendering in non-trivial ways. The discovery engine would need to handle a richer identity type (not just "email" or "username" but also "display_name", "bio_mention", etc.) and the UI would need to distinguish between high-confidence identities (explicit profile links) and lower-confidence ones (name extracted from bio text).

### When to revisit

Once the core extraction loop (check > extract > cache > reuse > stale > re-learn) is proven reliable on the initial site set, expand the LLM prompt to also return display names and bio-derived identities. This may also tie into the AI alias generation system — a discovered real name could seed additional username variant generation.

---

## Anti-bot measures & JS-heavy sites (deferred)

- Some high-value sites (Instagram, LinkedIn, Twitter/X) aggressively block automated requests. The current `aiohttp`-based approach won't work for these long-term.
- Sites that render profiles via JavaScript (SPAs) deliver empty HTML to non-browser clients, making extraction impossible without a headless browser.
- When needed: integrate a headless browser (Playwright, Puppeteer) for sites that require JS rendering or sophisticated anti-bot evasion. Keep the lightweight `aiohttp` path as default and only escalate to headless for sites that need it.

---

## Broader roadmap (ideas)

Not scheduled — capture tickets as needed: breach checks (e.g. HIBP), DNS/WHOIS, IP and phone pivots, deeper relationship mapping between identities.
