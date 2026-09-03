from __future__ import annotations

import hashlib
import itertools
from typing import TYPE_CHECKING

from .config import settings

if TYPE_CHECKING:
    from .models import Account

_dest_cycle = itertools.cycle([])


def _dest_tokens() -> list[str]:
    raw = settings.dest_github_tokens.strip()
    if raw:
        return [t.strip() for t in raw.split(",") if t.strip()]
    token = settings.dest_token
    return [token] if token else []


def refresh_dest_cycle() -> None:
    """Rebuild the dest-token round-robin after the tokens change."""
    global _dest_cycle
    tokens = _dest_tokens()
    _dest_cycle = itertools.cycle(tokens) if tokens else itertools.cycle([])


_refresh_dest_cycle = refresh_dest_cycle
refresh_dest_cycle()


def bucket_key(token: str) -> str:
    value = (token or "").strip()
    if not value:
        return "public"
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def token_hint(token: str) -> str:
    value = (token or "").strip()
    if not value:
        return ""
    if len(value) < 8:
        return "••••"
    return value[:4] + "••••" + value[-3:]


def poll_token_for_account(account: Account) -> str:
    login = account.origin_account.strip().lower()
    mapped = settings.poll_token_map_dict.get(login)
    if mapped:
        return mapped
    pool = settings.poll_tokens_list
    if pool and account.poll_token_index is not None and account.poll_token_index >= 0:
        return pool[account.poll_token_index % len(pool)]
    return settings.poll_token


def poll_auth_for_account(account: Account) -> str:
    login = account.origin_account.strip().lower()
    if login in settings.poll_token_map_dict:
        return "dedicated"
    if account.poll_token_index is not None and account.poll_token_index >= 0 and settings.poll_tokens_list:
        return "dedicated"
    token = poll_token_for_account(account)
    if not token:
        return "public"
    if token == settings.origin_token and settings.origin_token:
        return "origin"
    if token in _dest_tokens():
        return "dest"
    return "dedicated"


def assign_poll_token_index(existing_count: int) -> int | None:
    pool = settings.poll_tokens_list
    if not pool:
        return None
    return existing_count % len(pool)


def next_dest_token() -> str:
    tokens = _dest_tokens()
    if not tokens:
        return ""
    if len(tokens) == 1:
        return tokens[0]
    return next(_dest_cycle)


def unique_poll_token_count(accounts: list[Account]) -> int:
    keys = {bucket_key(poll_token_for_account(account)) for account in accounts}
    return max(1, len(keys))


def recommended_poll_seconds(account_count: int, token_count: int) -> int:
    """Safe poll gap given accounts and distinct poll-token buckets."""
    if account_count <= 0:
        return 10
    tokens = max(1, token_count)
    budget = 5000 * tokens * 0.75
    polls_per_hour = budget / (account_count * 1.5)
    if polls_per_hour <= 0:
        return 60
    interval = int(-(-3600 / polls_per_hour // 1))  # ceil
    return max(2, min(60, interval))
