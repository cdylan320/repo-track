from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import github
from ..config import settings
from ..database import get_db
from ..models import Account, Commit, Repo
from ..schemas import AccountCreate, AccountOut, AccountUpdate, RepoOut
from ..services import git_sync

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _today_start():
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def to_out(db: Session, account: Account, with_repos: bool = False) -> AccountOut:
    start = _today_start()
    today = (
        db.query(func.count(Commit.id))
        .filter(Commit.account_id == account.id, Commit.synced_at >= start)
        .scalar()
        or 0
    )
    synced = db.query(func.coalesce(func.sum(Repo.commits_synced), 0)).filter(Repo.account_id == account.id).scalar() or 0
    repo_count = db.query(func.count(Repo.id)).filter(Repo.account_id == account.id).scalar() or 0
    name = account.name or f"{account.origin_account} → {settings.dest_account}"
    repos = []
    if with_repos:
        rows = db.query(Repo).filter(Repo.account_id == account.id).order_by(Repo.name.asc()).all()
        repos = [RepoOut.model_validate(r) for r in rows]
    return AccountOut(
        id=account.id,
        origin_account=account.origin_account,
        origin_kind=account.origin_kind,
        dest_account=settings.dest_account,
        name=name,
        sync_mode=account.sync_mode,
        include_forks=account.include_forks,
        paused=account.paused,
        status=account.status,
        last_error=account.last_error,
        last_sync_at=account.last_sync_at,
        created_at=account.created_at,
        updated_at=account.updated_at,
        repo_count=repo_count,
        commits_synced=int(synced),
        commits_today=today,
        repos=repos,
    )


@router.get("", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db)):
    rows = db.query(Account).order_by(Account.created_at.desc()).all()
    return [to_out(db, row) for row in rows]


@router.post("", response_model=AccountOut)
def create_account(body: AccountCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    if not settings.dest_account:
        raise HTTPException(400, "DEST_GITHUB_ACCOUNT is not set in .env")
    if not settings.dest_token:
        raise HTTPException(400, "DEST_GITHUB_TOKEN is not set in .env")
    existing = db.query(Account).filter(Account.origin_account == body.origin_account).first()
    if existing:
        raise HTTPException(409, f"Already tracking {body.origin_account}")
    try:
        profile = github.account_profile(body.origin_account)
    except github.GithubError as exc:
        raise HTTPException(400, str(exc)) from exc
    account = Account(
        origin_account=body.origin_account,
        origin_kind=profile.get("type") or "User",
        name=body.name.strip(),
        sync_mode=body.sync_mode,
        include_forks=body.include_forks,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    background.add_task(git_sync.run_account, account.id)
    return to_out(db, account)


@router.get("/{account_id}", response_model=AccountOut)
def get_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    return to_out(db, account, with_repos=True)


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(account_id: int, body: AccountUpdate, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    data = body.model_dump(exclude_unset=True)
    if "origin_account" in data and data["origin_account"] != account.origin_account:
        try:
            profile = github.account_profile(data["origin_account"])
            data["origin_kind"] = profile.get("type") or "User"
        except github.GithubError as exc:
            raise HTTPException(400, str(exc)) from exc
    for key, value in data.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(account, key, value)
    db.commit()
    db.refresh(account)
    return to_out(db, account, with_repos=True)


@router.delete("/{account_id}")
def delete_account(account_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    git_sync.cancel_account(account_id)
    db.delete(account)
    db.commit()
    background.add_task(git_sync.wipe_account_clones, account_id)
    return {"ok": True}


@router.post("/{account_id}/sync")
async def sync_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    result = await git_sync.run_account(account_id)
    if not result.get("ok"):
        raise HTTPException(409, result.get("error") or "Sync failed")
    account = db.get(Account, account_id)
    return {"ok": True, "count": result.get("count", 0), "account": to_out(db, account, with_repos=True)}


@router.post("/sync-all")
async def sync_all():
    await git_sync.run_due_accounts()
    return {"ok": True}
