from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import github
from ..config import settings
from ..database import get_db
from ..models import Account, Commit, Event, Repo
from ..schemas import CommitOut, EventOut, OverviewOut
from ..services import git_sync

router = APIRouter(prefix="/api", tags=["activity"])


def _web_url(clone_url: str, label: str) -> str:
    """Browser URL for a repo: the stored clone url without .git, else built from owner/name."""
    url = (clone_url or "").strip()
    if url:
        return url[:-4] if url.endswith(".git") else url
    return f"https://github.com/{label}" if "/" in label else ""


def _today_start():
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def commit_out(commit: Commit, account: Account | None, repo: Repo | None) -> CommitOut:
    dest = settings.dest_account
    origin = account.origin_account if account else ""
    repo_name = repo.name if repo else ""
    origin_label = f"{origin}/{repo_name}" if origin and repo_name else origin
    dest_label = f"{dest}/{repo_name}" if dest and repo_name else dest
    return CommitOut(
        kind="commit",
        id=commit.id,
        account_id=commit.account_id,
        repo_id=commit.repo_id,
        sha=commit.sha,
        short_sha=commit.short_sha,
        message=commit.message,
        author_name=commit.author_name,
        author_email=commit.author_email,
        authored_at=commit.authored_at,
        files_changed=commit.files_changed,
        insertions=commit.insertions,
        deletions=commit.deletions,
        files_list=commit.files_list or "",
        synced_at=commit.synced_at,
        origin_label=origin_label,
        dest_label=dest_label,
        origin_url=_web_url(repo.origin_url if repo else "", origin_label),
        dest_url=_web_url(repo.dest_url if repo else "", dest_label),
        repo_name=repo_name,
        account_name=account.name if account else "",
    )


def new_repo_out(event: Event, account: Account | None, repo: Repo | None) -> CommitOut:
    dest = settings.dest_account
    origin = account.origin_account if account else ""
    repo_name = repo.name if repo else ""
    origin_label = f"{origin}/{repo_name}" if origin and repo_name else origin
    dest_label = f"{dest}/{repo_name}" if dest and repo_name else dest
    return CommitOut(
        kind="new-repo",
        id=event.id,
        account_id=event.account_id or 0,
        repo_id=event.repo_id or 0,
        sha="",
        short_sha="new",
        message=event.message,
        author_name="",
        author_email="",
        authored_at=event.created_at,
        files_changed=0,
        insertions=0,
        deletions=0,
        files_list="",
        synced_at=event.created_at,
        origin_label=origin_label,
        dest_label=dest_label,
        origin_url=_web_url(repo.origin_url if repo else "", origin_label),
        dest_url=_web_url(repo.dest_url if repo else "", dest_label),
        repo_name=repo_name,
        account_name=account.name if account else "",
    )


@router.get("/overview", response_model=OverviewOut)
def overview(db: Session = Depends(get_db)):
    start = _today_start()
    account_count = db.query(func.count(Account.id)).scalar() or 0
    paused_count = db.query(func.count(Account.id)).filter(Account.paused.is_(True)).scalar() or 0
    error_count = db.query(func.count(Account.id)).filter(Account.status == "error").scalar() or 0
    repo_count = db.query(func.count(Repo.id)).scalar() or 0
    commits_today = db.query(func.count(Commit.id)).filter(Commit.synced_at >= start).scalar() or 0
    commits_total = db.query(func.count(Commit.id)).scalar() or 0
    last_sync = db.query(func.max(Account.last_sync_at)).scalar()
    return OverviewOut(
        account_count=account_count,
        pair_count=account_count,
        active_count=account_count - paused_count,
        paused_count=paused_count,
        error_count=error_count,
        repo_count=repo_count,
        commits_today=commits_today,
        commits_total=commits_total,
        last_sync_at=last_sync,
        poll_interval_seconds=settings.poll_interval_seconds,
        discord_configured=bool(settings.discord_webhook_url.strip()),
        dest_account=settings.dest_account,
        dest_token_configured=bool(settings.dest_token),
        origin_token_configured=bool(settings.origin_token),
        git_token_configured=bool(settings.dest_token),
        worker_running=git_sync.is_running(),
        next_tick_at=git_sync.next_tick_at(),
        github_paused_until=(
            datetime.fromtimestamp(github.reset_at(), tz=timezone.utc) if github.reset_at() else None
        ),
        github_remaining=github.remaining(),
    )


def _sort_ts(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@router.get("/activity", response_model=list[CommitOut])
def activity(
    account_id: int | None = None,
    pair_id: int | None = None,
    limit: int = Query(80, ge=1, le=200),
    db: Session = Depends(get_db),
):
    commit_q = db.query(Commit).order_by(Commit.synced_at.desc(), Commit.id.desc())
    event_q = db.query(Event).filter(Event.kind == "new-repo").order_by(Event.created_at.desc(), Event.id.desc())
    track_id = account_id or pair_id
    if track_id is not None:
        commit_q = commit_q.filter(Commit.account_id == track_id)
        event_q = event_q.filter(Event.account_id == track_id)
    commits = commit_q.limit(limit).all()
    events = event_q.limit(limit).all()
    acc_ids = {row.account_id for row in commits} | {row.account_id for row in events if row.account_id}
    repo_ids = {row.repo_id for row in commits} | {row.repo_id for row in events if row.repo_id}
    accounts = {a.id: a for a in db.query(Account).filter(Account.id.in_(acc_ids)).all()} if acc_ids else {}
    repos = {r.id: r for r in db.query(Repo).filter(Repo.id.in_(repo_ids)).all()} if repo_ids else {}
    items: list[tuple[datetime, int, str, CommitOut]] = []
    for row in commits:
        out = commit_out(row, accounts.get(row.account_id), repos.get(row.repo_id))
        items.append((row.synced_at, row.id, "commit", out))
    for row in events:
        out = new_repo_out(row, accounts.get(row.account_id) if row.account_id else None, repos.get(row.repo_id) if row.repo_id else None)
        items.append((row.created_at, row.id, "new-repo", out))
    items.sort(key=lambda item: (_sort_ts(item[0]), item[1]), reverse=True)
    return [item[3] for item in items[:limit]]


@router.get("/logs", response_model=list[EventOut])
def logs(
    account_id: int | None = None,
    pair_id: int | None = None,
    limit: int = Query(60, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(Event).order_by(Event.created_at.desc(), Event.id.desc())
    track_id = account_id or pair_id
    if track_id is not None:
        query = query.filter(Event.account_id == track_id)
    rows = query.limit(limit).all()
    acc_ids = {row.account_id for row in rows if row.account_id}
    accounts = {a.id: a for a in db.query(Account).filter(Account.id.in_(acc_ids)).all()} if acc_ids else {}
    dest = settings.dest_account
    out: list[EventOut] = []
    for row in rows:
        account = accounts.get(row.account_id) if row.account_id else None
        out.append(
            EventOut(
                id=row.id,
                account_id=row.account_id,
                repo_id=row.repo_id,
                kind=row.kind,
                message=row.message,
                detail=row.detail,
                created_at=row.created_at,
                origin_label=account.origin_account if account else "",
                dest_label=dest,
            )
        )
    return out
