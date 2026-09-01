from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..config import settings
from ..events import bus
from .. import github
from . import git_sync

log = logging.getLogger("relay.scheduler")
scheduler = AsyncIOScheduler()


async def _tick() -> None:
    git_sync.set_next_tick(datetime.now(timezone.utc) + timedelta(seconds=settings.poll_interval_seconds))
    await bus.publish(
        "tick",
        {
            "next_tick_at": git_sync.next_tick_at().isoformat() if git_sync.next_tick_at() else None,
            "github_paused_until": github.reset_iso(),
            "github_remaining": github.remaining(),
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
