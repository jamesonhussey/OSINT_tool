"""Rule cache management.

Loads, merges, and saves extraction rules from default_rules.json (shipped)
and local_rules.json (user-learned).  Local rules take precedence per-domain.
"""
import json
from pathlib import Path

from osint_tool.data.rule_schema import SiteRule

DEFAULT_RULES_PATH = Path(__file__).parent / "default_rules.json"
LOCAL_RULES_PATH = Path(__file__).parent.parent.parent / "local_rules.json"


class RuleCache:
    def __init__(self) -> None:
        self._rules: dict[str, SiteRule] = {}
        self._load()

    def _load(self) -> None:
        self._rules = {}
        for rule in _load_rules_file(DEFAULT_RULES_PATH):
            self._rules[rule.domain] = rule
        for rule in _load_rules_file(LOCAL_RULES_PATH):
            self._rules[rule.domain] = rule

    def get(self, domain: str) -> SiteRule | None:
        return self._rules.get(domain)

    def save_rule(self, rule: SiteRule) -> None:
        """Save/update a rule in local_rules.json."""
        self._rules[rule.domain] = rule
        _save_local_rule(rule)

    def mark_needs_relearn(self, domain: str) -> None:
        rule = self._rules.get(domain)
        if rule:
            rule.needs_relearn = True
            _save_local_rule(rule)
        else:
            new_rule = SiteRule(domain=domain, needs_relearn=True)
            self._rules[domain] = new_rule
            _save_local_rule(new_rule)

    def increment_fail_count(self, domain: str) -> int:
        rule = self._rules.get(domain)
        if not rule:
            rule = SiteRule(domain=domain)
            self._rules[domain] = rule
        rule.fail_count += 1
        _save_local_rule(rule)
        return rule.fail_count

    def mark_skip(self, domain: str, reason: str) -> None:
        rule = self._rules.get(domain)
        if not rule:
            rule = SiteRule(domain=domain)
            self._rules[domain] = rule
        rule.skip = True
        rule.skip_reason = reason
        _save_local_rule(rule)

    def reload(self) -> None:
        self._load()


_cache: RuleCache | None = None


def get_rule_cache() -> RuleCache:
    global _cache
    if _cache is None:
        _cache = RuleCache()
    return _cache


def reset_local_rules() -> None:
    """Delete local_rules.json and reload merged rules (bundled defaults only for local overrides)."""
    if LOCAL_RULES_PATH.exists():
        LOCAL_RULES_PATH.unlink()
    global _cache
    if _cache is not None:
        _cache.reload()
    else:
        _cache = RuleCache()


def _load_rules_file(path: Path) -> list[SiteRule]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "rules" in data:
            return [SiteRule.from_dict(r) for r in data["rules"]]
        return []
    except Exception:
        return []


def _save_local_rule(rule: SiteRule) -> None:
    """Update a single rule in local_rules.json (preserving others)."""
    existing: dict[str, dict] = {}
    if LOCAL_RULES_PATH.exists():
        try:
            data = json.loads(LOCAL_RULES_PATH.read_text(encoding="utf-8"))
            for r in data.get("rules", []):
                existing[r["domain"]] = r
        except Exception:
            pass
    existing[rule.domain] = rule.to_dict()
    LOCAL_RULES_PATH.write_text(
        json.dumps({"rules": list(existing.values())}, indent=2),
        encoding="utf-8",
    )
