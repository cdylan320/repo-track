from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..github import parse_account
from ..models import AppMeta
from ..schemas import DiscordTestResult, SettingsOut, SettingsUpdate
from ..services import discord, scheduler
from ..services.discord import webhook_hint

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _token_hint(token: str) -> str:
    if not token:
        return ""
    if len(token) < 8:
        return "••••"
    return token[:4] + "••••" + token[-3:]


@router.get("", response_model=SettingsOut)
def get_settings():
    dest = settings.dest_token
    origin = settings.origin_token
    return SettingsOut(
        poll_interval_seconds=settings.poll_interval_seconds,
        discord_configured=bool(settings.discord_webhook_url.strip()),
        discord_webhook_hint=webhook_hint(settings.discord_webhook_url),
        dest_account=settings.dest_account,
        dest_token_configured=bool(dest),
        dest_token_hint=_token_hint(dest),
        origin_token_configured=bool(origin),
        origin_token_hint=_token_hint(origin),
        git_token_configured=bool(dest),
        git_token_hint=_token_hint(dest),
    )


@router.patch("", response_model=SettingsOut)
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db)):
    if body.poll_interval_seconds is not None:
        scheduler.reschedule(body.poll_interval_seconds)
        row = db.get(AppMeta, "poll_interval_seconds")
        if row:
            row.value = str(body.poll_interval_seconds)
        else:
            db.add(AppMeta(key="poll_interval_seconds", value=str(body.poll_interval_seconds)))
        db.commit()
    return get_settings()


@router.post("/discord-test", response_model=DiscordTestResult)
async def discord_test():
    ok, message = await discord.notify_test()
    if not ok:
        raise HTTPException(400, message)
    return DiscordTestResult(ok=True, message="Test message sent")


@router.get("/parse-repo")
def parse_repo(url: str):
    return {"label": parse_account(url), "url": url}
