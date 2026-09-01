from __future__ import annotations

import logging
import time

from .. import github
from ..events import bus
from ..tokens import bucket_key, token_hint
from . import discord

log = logging.getLogger("relay.ratelimit")

# One alert burst per token bucket per GitHub reset window.
_alerted_until: dict[str, float] = {}


def _episode_key(token: str) -> tuple[str, float]:
    key = bucket_key(token)
    until = github.reset_at(token) or time.time() + 3600
    return key, until


def log_rate_limit(origin: str, token: str, *, blocked: bool = False) -> None:
    hint = token_hint(token) or "public"
    remaining = github.remaining(token)
    resume = github.reset_iso(token) or "unknown"
    if blocked:
        log.warning(
            "GitHub rate limit ACTIVE — origin=%s token=%s remaining=%s resumes=%s",
            origin,
            hint,
            remaining,
            resume,
        )
    else:
        log.warning(
            "GitHub rate limit HIT — origin=%s token=%s remaining=%s resumes=%s",
            origin,
            hint,
            remaining,
            resume,
        )


async def emit_rate_limit(
    *,
    account_id: int,
    origin: str,
    token: str,
    github_buckets: list[dict] | None = None,
    rate_limited_count: int | None = None,
) -> bool:
    """Discord + toast only on first hit per reset window. UI updates every poll via tick SSE."""
    key, until = _episode_key(token)
    now = time.time()
    if key in _alerted_until and _alerted_until[key] > now:
        log.info(
            "poll blocked — origin=%s token=%s (still rate-limited until reset)",
            origin,
            token_hint(token),
        )
        return False
    _alerted_until[key] = until
    log_rate_limit(origin, token)
    await discord.notify_rate_limit(origin, token, resume=github.reset_iso(token))
    await bus.publish(
        "rate_limit",
        _payload(account_id, origin, token, github_buckets, rate_limited_count, new_episode=True),
    )
    return True


def _payload(
    account_id: int,
    origin: str,
    token: str,
    github_buckets: list[dict] | None,
    rate_limited_count: int | None,
    *,
    new_episode: bool = False,
) -> dict:
    return {
        "account_id": account_id,
        "origin": origin,
        "token_hint": token_hint(token),
        "github_paused_until": github.reset_iso(token) or github.reset_iso(),
        "github_remaining": github.remaining(token),
        "github_buckets": github_buckets or [],
        "rate_limited_count": rate_limited_count,
        "new_episode": new_episode,
    }


def log_poll_cycle(*, account_count: int, rate_limited_count: int, api_remaining: int) -> None:
    """Called every poll cycle — rate limit is checked on every tick."""
    paused = github.reset_iso() or "—"
    if rate_limited_count > 0:
        log.warning(
            "poll cycle — %s/%s origins rate-limited, %s API calls left, resumes ~%s",
            rate_limited_count,
            account_count,
            api_remaining,
            paused,
        )
    elif api_remaining < 300:
        log.warning(
            "poll cycle — %s/%s origins ok, API budget low (%s left)",
            account_count,
            account_count,
            api_remaining,
        )
    else:
        log.info(
            "poll cycle — %s origins ok, %s API calls left",
            account_count,
            api_remaining,
        )


def count_rate_limited_accounts(accounts) -> int:
    from ..tokens import poll_token_for_account

    total = 0
    for account in accounts:
        if github.is_blocked(poll_token_for_account(account)):
            total += 1
    return total


def bucket_payload(accounts) -> tuple[list[dict], int]:
    from ..tokens import bucket_key, poll_token_for_account

    labels: dict[str, list[str]] = {}
    for account in accounts:
        token = poll_token_for_account(account)
        labels.setdefault(bucket_key(token), []).append(account.origin_account)
    buckets = github.bucket_summaries(labels)
    return buckets, count_rate_limited_accounts(accounts)
