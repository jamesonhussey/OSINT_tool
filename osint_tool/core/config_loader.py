"""Shared config: project root, config.json, Anthropic API key resolution.

Precedence for the effective API key at runtime:
1. ``ANTHROPIC_API_KEY`` environment variable (after optional ``.env`` load)
2. ``anthropic_api_key`` in ``config.json`` next to the project root

``load_dotenv_once()`` loads ``.env`` from the project root once (idempotent).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Repo root (parent of the ``osint_tool`` package), same as modules use via parent.parent.parent
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH: Path = PROJECT_ROOT / "config.json"

_dotenv_loaded: bool = False

KeySource = Literal["environment", "file", "none"]


def load_dotenv_once() -> None:
    """Load ``.env`` from project root if present. Safe to call multiple times."""
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    load_dotenv(PROJECT_ROOT / ".env")
    _dotenv_loaded = True


def load_config_json() -> dict:
    """Read ``config.json`` if present; tolerate missing or invalid JSON."""
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_anthropic_api_key() -> str | None:
    """Effective Anthropic API key: env wins, then ``config.json``."""
    load_dotenv_once()
    env_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if env_key:
        return env_key
    cfg = load_config_json()
    raw = cfg.get("anthropic_api_key")
    if raw is None:
        return None
    s = str(raw).strip()
    return s if s else None


def api_key_source() -> KeySource:
    """Where the *effective* key would come from (for API/UI disclosure)."""
    load_dotenv_once()
    env_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if env_key:
        return "environment"
    cfg = load_config_json()
    raw = cfg.get("anthropic_api_key")
    if raw is not None and str(raw).strip():
        return "file"
    return "none"
