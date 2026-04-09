"""
Multi-hop discovery engine.

Performs a breadth-first search starting from an initial email or username.
Each found account is passed to a platform resolver which may yield new
identities (emails or usernames). New identities are queued as additional seeds.

Usage:
    engine = DiscoveryEngine("john@example.com", hop_cap=100)
    async for event_type, event_data in engine.run():
        ...  # stream to client

Event types (in order of emission):
    start               — search began
    hop_start           — a seed is about to be processed
    gravatar            — gravatar result for an email seed
    account_result      — one platform check result
    identity_discovered — a new identity was extracted from a found account
    hop_complete        — seed finished processing
    cap_reached         — hop cap hit, stopping early
    done                — all seeds exhausted (or cap hit)
"""
from collections import deque
from dataclasses import dataclass

from osint_tool.core.engine import is_email, search_email, search_username
from osint_tool.core.models import AccountStatus
from osint_tool.modules.resolvers import resolve_gravatar, resolve_platform


@dataclass
class _Item:
    seed: str
    seed_type: str       # 'email' | 'username'
    hop: int
    parent_seed: str | None
    parent_platform: str | None


def _serialize_gravatar(g) -> dict:
    return {
        'display_name': g.display_name,
        'profile_url': g.profile_url,
        'avatar_url': g.avatar_url,
        'about': g.about,
        'location': g.location,
        'urls': g.urls or [],
    }


class DiscoveryEngine:
    def __init__(self, initial_query: str, hop_cap: int | None = 100):
        self.hop_cap = hop_cap
        self.seen_usernames: set[str] = set()
        self.seen_emails: set[str] = set()
        self._queue: deque[_Item] = deque()
        self._enqueue(initial_query.strip(), hop=0, parent_seed=None, parent_platform=None)

    # ── Queue management ──────────────────────────────────────────────────────

    def _enqueue(
        self,
        value: str,
        hop: int,
        parent_seed: str | None,
        parent_platform: str | None,
    ) -> bool:
        """Add value to the queue if not already seen. Returns True if queued."""
        if not value:
            return False
        key = value.lower()
        seed_type = 'email' if is_email(value) else 'username'

        if seed_type == 'email':
            if key in self.seen_emails:
                return False
            self.seen_emails.add(key)
        else:
            if key in self.seen_usernames:
                return False
            self.seen_usernames.add(key)

        self._queue.append(_Item(
            seed=value,
            seed_type=seed_type,
            hop=hop,
            parent_seed=parent_seed,
            parent_platform=parent_platform,
        ))
        return True

    def _mark_username_seen(self, username: str) -> None:
        self.seen_usernames.add(username.lower())

    # ── Main generator ────────────────────────────────────────────────────────

    async def run(self):
        hops_done = 0
        yield 'start', {}

        while self._queue:
            if self.hop_cap is not None and hops_done >= self.hop_cap:
                yield 'cap_reached', {'cap': self.hop_cap}
                break

            item = self._queue.popleft()
            hops_done += 1

            yield 'hop_start', {
                'hop': item.hop,
                'seed': item.seed,
                'seed_type': item.seed_type,
                'parent_seed': item.parent_seed,
                'parent_platform': item.parent_platform,
                'queue_remaining': len(self._queue),
            }

            # ── Run the search for this seed ──────────────────────────────

            if item.seed_type == 'email':
                result = await search_email(item.seed)
                # Prevent re-processing derived username variations as future seeds
                for u in result.derived_usernames:
                    self._mark_username_seen(u)
            else:
                result = await search_username(item.seed)

            # ── Gravatar (email seeds only) ───────────────────────────────

            if result.gravatar:
                yield 'gravatar', {
                    'hop': item.hop,
                    'seed': item.seed,
                    'data': _serialize_gravatar(result.gravatar),
                }
                for identity in resolve_gravatar(result.gravatar):
                    queued = self._enqueue(
                        identity['value'],
                        hop=item.hop + 1,
                        parent_seed=item.seed,
                        parent_platform='Gravatar',
                    )
                    if queued:
                        yield 'identity_discovered', {
                            'hop': item.hop,
                            'source_seed': item.seed,
                            'source_platform': 'Gravatar',
                            'value': identity['value'],
                            'value_type': 'email' if is_email(identity['value']) else 'username',
                            'source_detail': identity.get('source', ''),
                            'hint_platform': identity.get('hint_platform'),
                        }

            # ── Account results + resolvers ───────────────────────────────

            for account in result.accounts:
                yield 'account_result', {
                    'hop': item.hop,
                    'seed': item.seed,
                    'platform': account.platform.value,
                    'username': account.username,
                    'url': account.url,
                    'status': account.status.value,
                }

                if account.status == AccountStatus.FOUND:
                    identities, extraction_activity = await resolve_platform(
                        account.platform, account.username,
                        html_body=account.html_body, url=account.url,
                    )
                    if extraction_activity:
                        yield 'extraction_activity', {
                            'hop': item.hop,
                            'seed': item.seed,
                            'username': account.username,
                            'url': account.url,
                            **extraction_activity,
                        }
                    for identity in identities:
                        queued = self._enqueue(
                            identity['value'],
                            hop=item.hop + 1,
                            parent_seed=account.username,
                            parent_platform=account.platform.value,
                        )
                        if queued:
                            yield 'identity_discovered', {
                                'hop': item.hop,
                                'source_seed': account.username,
                                'source_platform': account.platform.value,
                                'value': identity['value'],
                                'value_type': 'email' if is_email(identity['value']) else 'username',
                                'source_detail': identity.get('source', ''),
                                'hint_platform': identity.get('hint_platform'),
                            }

            yield 'hop_complete', {
                'hop': item.hop,
                'seed': item.seed,
                'queue_remaining': len(self._queue),
            }

        yield 'done', {
            'total_hops': hops_done,
            'total_usernames': len(self.seen_usernames),
            'total_emails': len(self.seen_emails),
        }
