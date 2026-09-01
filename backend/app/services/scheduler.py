from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..config import settings
from ..database import SessionLocal
from ..events import bus
from .. import github
from . import git_sync
from .rate_alerts import bucket_payload, log_poll_cycle

log = logging.getLogger("relay.scheduler")
scheduler = AsyncIOScheduler()


async def _tick() -> None:
    git_sync.set_next_tick(datetime.now(timezone.utc) + timedelta(seconds=settings.poll_interval_seconds))
    db = SessionLocal()
    accounts = []
    buckets: list[dict] = []
    limited = 0
    api_remaining = github.remaining()
    try:
        from ..models import Account

        accounts = db.query(Account).order_by(Account.id.asc()).all()
        buckets, limited = bucket_payload(accounts)
        api_remaining = github.remaining()
    finally:
        db.close()
    log_poll_cycle(
        account_count=len(accounts),
        rate_limited_count=limited if accounts else 0,
        api_remaining=api_remaining,
    )
    await bus.publish(
        "tick",
        {
            "next_tick_at": git_sync.next_tick_at().isoformat() if git_sync.next_tick_at() else None,
            "github_paused_until": github.reset_iso(),
            "github_remaining": api_remaining,
            "rate_limited_count": limited if accounts else 0,
            "github_buckets": buckets if accounts else [],
        },
    )
    await git_sync.run_due_accounts()


def start() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        _tick,
        "interval",
        seconds=max(2, settings.poll_interval_seconds),
        id="relay-poll",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=8),
    )
    scheduler.start()
    git_sync.set_running(True)
    git_sync.set_next_tick(datetime.now(timezone.utc) + timedelta(seconds=8))
    log.info("scheduler started, interval=%ss", settings.poll_interval_seconds)


def reschedule(seconds: int) -> None:
    seconds = max(2, min(3600, seconds))
    settings.poll_interval_seconds = seconds
    if scheduler.running and scheduler.get_job("relay-poll"):
        scheduler.reschedule_job("relay-poll", trigger="interval", seconds=seconds)
    git_sync.set_next_tick(datetime.now(timezone.utc) + timedelta(seconds=seconds))


def stop() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
    git_sync.set_running(False)
