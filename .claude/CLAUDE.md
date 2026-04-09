# OSINT Aggregation CLI Tool

## Overview
A Python CLI tool for penetration testing that consolidates a target's online presence from a starting piece of information (email, username, phone number).

## Current Scope (Phase 1)
- **Username enumeration**: Given an email or username, check if accounts exist on major social media platforms (GitHub, Twitter/X, Instagram, Reddit, LinkedIn, etc.) by probing profile URLs or public APIs.
- **Gravatar lookup**: Hash email, check Gravatar for linked profile info and avatar.
- **Email-based discovery**: Derive username variations from email handle, run through username enumeration.
- **Free/no-auth sources only** for now. Architecture should support paid API integrations later.

## Future Phases
- Web UI frontend
- Breach checking (HIBP or similar, requires API key)
- DNS/WHOIS lookups
- IP address investigation
- Phone number lookups
- Email-to-email relationship mapping (paid APIs)

## Tech Stack
- Python
- CLI framework (click or argparse)
- Modular architecture for easy data source expansion

## Project Structure
```
osint_tool/
  cli.py              # CLI entry point
  core/
    engine.py          # Orchestrates lookups
    models.py          # Data models for results
  modules/
    username_enum.py   # Check username across platforms
    gravatar.py        # Gravatar lookup
    email_utils.py     # Email-based discovery
  output/
    formatter.py       # Pretty terminal output
```

## Design Principles
- Modular: each data source is its own module, easy to add/remove
- Extensible: architecture supports adding paid API integrations later
- CLI-first: clean terminal output, web UI can come later

## Planning & hardening
- **Backlog and deferred security work:** see [`docs/PLANNING.md`](../docs/PLANNING.md) (API keys, gitignore, web exposure, rate limits, etc.).
