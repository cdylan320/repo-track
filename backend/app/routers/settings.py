from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import github
from ..config import settings
from ..database import get_db
from ..models import AppMeta, Account
from ..schemas import DiscordTestResult, GithubBucketOut, SettingsOut, SettingsUpdate
from ..services import discord, scheduler
from ..services.discord import webhook_hint
from ..tokens import bucket_key, poll_token_for_account, recommended_poll_seconds, token_hint, unique_poll_token_count

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _token_hint(token: str) -> str:
    if not token:
        return ""
    if len(token) < 8:
        return "••••"
    return token[:4] + "••••" + token[-3:]


@router.get("", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    dest = settings.dest_token
    origin = settings.origin_token
    accounts = db.query(Account).order_by(Account.id.asc()).all()
    labels: dict[str, list[str]] = {}
    for account in accounts:
        token = poll_token_for_account(account)
        labels.setdefault(bucket_key(token), []).append(account.origin_account)
    token_count = unique_poll_token_count(accounts) if accounts else max(1, len(settings.poll_tokens_list) or (1 if dest else 0))
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
        poll_auth=github.poll_auth(),
        github_remaining=github.remaining(),
        github_paused_until=github.reset_iso(),
        poll_tokens_configured=len(settings.poll_tokens_list),
        poll_token_map_configured=len(settings.poll_token_map_dict),
        dest_tokens_configured=len(settings.dest_tokens_list),
        recommended_poll_seconds=recommended_poll_seconds(len(accounts), token_count),
        github_buckets=[GithubBucketOut(**row) for row in github.bucket_summaries(labels)],
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
    return get_settings(db)


@router.post("/discord-test", response_model=DiscordTestResult)
async def discord_test():
    ok, message = await discord.notify_test()
    if not ok:
        raise HTTPException(400, message)
    return DiscordTestResult(ok=True, message="Test message sent")


@router.get("/parse-repo")
def parse_repo(url: str):
    return {"label": github.parse_account(url), "url": url}
