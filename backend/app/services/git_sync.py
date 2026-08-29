from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from .. import github
from ..config import settings
from ..database import SessionLocal
from ..events import bus
from ..gitutil import inject_token
from ..models import Account, Commit, Event, Repo, utcnow
from . import discord

log = logging.getLogger("relay.sync")

_locks: dict[int, asyncio.Lock] = {}
_cancel: set[int] = set()
_running = False
_next_tick: datetime | None = None
_scrubbed_descriptions = False


def is_running() -> bool:
    return _running


def next_tick_at() -> datetime | None:
    return _next_tick


def set_next_tick(value: datetime | None) -> None:
    global _next_tick
    _next_tick = value


def set_running(value: bool) -> None:
    global _running
    _running = value


def cancel_account(account_id: int) -> None:
    _cancel.add(account_id)


def cancelled(account_id: int) -> bool:
    return account_id in _cancel


def clear_cancel(account_id: int) -> None:
    _cancel.discard(account_id)


def account_lock(account_id: int) -> asyncio.Lock:
    if account_id not in _locks:
        _locks[account_id] = asyncio.Lock()
    return _locks[account_id]


def clone_dir(account_id: int, repo_name: str | None = None) -> Path:
    path = settings.clones_dir / str(account_id)
    if repo_name:
        path = path / repo_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = "echo"
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=settings.git_timeout_seconds,
        env=env,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _git(repo: Repo, args: list[str]) -> tuple[int, str, str]:
    return _run(["git", *args], cwd=clone_dir(repo.account_id, repo.name))


def _clean_err(err: str) -> str:
    if not err:
        return ""
    lines = []
    for line in err.splitlines():
        if "x-access-token:" in line or "oauth2:" in line:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _ensure_clone(account: Account, repo: Repo) -> None:
    folder = clone_dir(account.id, repo.name)
    git_dir = folder / ".git"
    origin = inject_token(repo.origin_url, settings.origin_token)
    dest = inject_token(repo.dest_url, settings.dest_token)

    if not git_dir.exists():
        code, _, err = _run(["git", "clone", "--origin", "origin", origin, str(folder)])
        if code != 0:
            raise RuntimeError(_clean_err(err) or "git clone failed")
    else:
        code, _, err = _git(repo, ["remote", "set-url", "origin", origin])
        if code != 0:
            raise RuntimeError(_clean_err(err) or "could not update origin remote")

    code, remotes, err = _git(repo, ["remote"])
    if code != 0:
        raise RuntimeError(_clean_err(err) or "could not list remotes")
    if "dest" not in remotes.split():
        code, _, err = _git(repo, ["remote", "add", "dest", dest])
        if code != 0:
            raise RuntimeError(_clean_err(err) or "could not add dest remote")
    else:
        _git(repo, ["remote", "set-url", "dest", dest])


def _parse_commits(raw: str) -> list[dict]:
    commits: list[dict] = []
    if not raw.strip():
        return commits
    for block in raw.split("\x1e"):
        block = block.strip()
        if not block:
            continue
        header, _, stats = block.partition("\n")
        parts = header.split("\x1f")
        if len(parts) < 5:
            continue
        sha, message, name, email, date_raw = parts[:5]
        files = insertions = deletions = 0
        names: list[str] = []
        for line in stats.splitlines():
            bits = line.split("\t")
            if len(bits) < 3:
                continue
            files += 1
            if bits[0].isdigit():
                insertions += int(bits[0])
            if bits[1].isdigit():
                deletions += int(bits[1])
            names.append(bits[2])
        authored_at = None
        if date_raw:
            try:
                authored_at = datetime.fromisoformat(date_raw)
            except ValueError:
                authored_at = None
        commits.append(
            {
                "sha": sha,
                "short_sha": sha[:7],
                "message": message,
                "author_name": name,
                "author_email": email,
                "authored_at": authored_at,
                "files_changed": files,
                "insertions": insertions,
                "deletions": deletions,
                "files_list": ", ".join(names[:16]),
            }
        )
    return commits


def _log_range(repo: Repo, rev: str | list[str]) -> list[dict]:
    pretty = "%H%x1f%s%x1f%an%x1f%ae%x1f%aI"
    extra = rev if isinstance(rev, list) else [rev]
    code, out, err = _git(
        repo,
        ["log", "--reverse", "--numstat", f"--pretty=format:\x1e{pretty}", *extra],
    )
    if code != 0:
        raise RuntimeError(_clean_err(err) or "git log failed")
    return _parse_commits(out)


def _checkout_branch(repo: Repo) -> None:
    branch = repo.default_branch or "main"
    code, _, err = _git(repo, ["checkout", "-B", f"relay/{branch}", f"origin/{branch}"])
    if code == 0:
        return
    for fallback in (branch, "main", "master"):
        code, _, _ = _git(repo, ["checkout", "-B", f"relay/{fallback}", f"origin/{fallback}"])
        if code == 0:
            repo.default_branch = fallback
            return
    raise RuntimeError(_clean_err(err) or f"branch '{branch}' not found on origin")


def _push_dest(account: Account, repo: Repo) -> None:
    branch = repo.default_branch or "main"
    refspec = f"HEAD:refs/heads/{branch}"
    if account.sync_mode == "force":
        args = ["push", "--force", "dest", refspec]
    else:
        args = ["push", "dest", refspec]
    code, _, err = _git(repo, args)
    if code != 0:
        raise RuntimeError(_clean_err(err) or "git push dest failed")


def _is_sha(value: str) -> bool:
    value = (value or "").strip()
    return len(value) >= 7 and all(c in "0123456789abcdefABCDEF" for c in value)


def _baseline_repo(account: Account, repo: Repo, remote: dict) -> None:
    sha = github.tip_sha(account.origin_account, repo.name, remote["default_branch"] or repo.default_branch)
    repo.last_sha = sha
    repo.pushed_at = remote.get("pushed_at") or repo.pushed_at
    repo.default_branch = remote.get("default_branch") or repo.default_branch
    repo.mirrored = False
    repo.status = "idle"
    repo.last_error = ""
    repo.last_sync_at = utcnow()


def _open_new_repo(account: Account, repo: Repo, remote: dict) -> str:
    github.ensure_dest_repo(repo.name, repo.private, remote.get("description") or "")
    repo.mirrored = True
    repo.pushed_at = remote.get("pushed_at") or ""
    if remote.get("empty"):
        repo.last_sha = ""
        repo.status = "idle"
        repo.last_error = ""
        repo.last_sync_at = utcnow()
        return ""
    _ensure_clone(account, repo)
    code, _, err = _git(repo, ["fetch", "origin", "--prune"])
    if code != 0:
        raise RuntimeError(_clean_err(err) or "git fetch origin failed")
    _checkout_branch(repo)
    code, tip, err = _git(repo, ["rev-parse", "HEAD"])
    if code != 0 or not tip:
        repo.last_sha = ""
        repo.status = "idle"
        repo.last_sync_at = utcnow()
        return ""
    _push_dest(account, repo)
    repo.last_sha = tip
    repo.status = "idle"
    repo.last_error = ""
    repo.last_sync_at = utcnow()
    return tip


def _relay_new_commits(account: Account, repo: Repo, remote: dict) -> tuple[list[dict], str]:
    github.ensure_dest_repo(repo.name, repo.private, remote.get("description") or "")
    _ensure_clone(account, repo)
    code, _, err = _git(repo, ["fetch", "origin", "--prune"])
    if code != 0:
        raise RuntimeError(_clean_err(err) or "git fetch origin failed")
    _checkout_branch(repo)
    code, tip, err = _git(repo, ["rev-parse", "HEAD"])
    if code != 0 or not tip:
        raise RuntimeError(_clean_err(err) or "could not resolve HEAD")
    if repo.last_sha and repo.last_sha == tip:
        repo.pushed_at = remote.get("pushed_at") or repo.pushed_at
        return [], tip
    if repo.last_sha and _is_sha(repo.last_sha):
        commits = _log_range(repo, f"{repo.last_sha}..HEAD")
    else:
        commits = _log_range(repo, ["-n", "20", "HEAD"])
    if not commits:
        repo.last_sha = tip
        repo.pushed_at = remote.get("pushed_at") or repo.pushed_at
        return [], tip
    _push_dest(account, repo)
    repo.mirrored = True
    repo.last_sha = tip
    repo.pushed_at = remote.get("pushed_at") or repo.pushed_at
    repo.status = "idle"
    repo.last_error = ""
    repo.last_sync_at = utcnow()
    return commits, tip


def _record_event(db: Session, account: Account | None, kind: str, message: str, detail: str = "", repo: Repo | None = None) -> None:
    db.add(
        Event(
            account_id=account.id if account else None,
            repo_id=repo.id if repo else None,
            kind=kind,
            message=message,
            detail=detail[:4000],
        )
    )


def _upsert_repo(db: Session, account: Account, remote: dict) -> tuple[Repo, bool]:
    row = db.query(Repo).filter(Repo.account_id == account.id, Repo.name == remote["name"]).first()
    created = False
    if not row:
        row = Repo(
            account_id=account.id,
            name=remote["name"],
            origin_url=github.origin_https(account.origin_account, remote["name"]),
            dest_url=github.dest_https(remote["name"]),
            default_branch=remote["default_branch"],
            private=remote["private"],
        )
        db.add(row)
        db.flush()
        created = True
    else:
        row.origin_url = github.origin_https(account.origin_account, remote["name"])
        row.dest_url = github.dest_https(remote["name"])
        row.default_branch = remote["default_branch"] or row.default_branch
        row.private = remote["private"]
    return row, created


def sync_account_now(db: Session, account: Account) -> dict:
    global _scrubbed_descriptions
    account.status = "syncing"
    account.last_error = ""
    db.commit()
    db.refresh(account)

    new_repos: list[Repo] = []
    commit_groups: list[dict] = []
    errors: list[str] = []
    stored_total = 0

    first_account = True
    try:
        if not _scrubbed_descriptions:
            try:
                github.scrub_relay_descriptions()
                _scrubbed_descriptions = True
            except Exception:
                log.exception("could not clear dest repo descriptions")
        first_account = db.query(Repo).filter(Repo.account_id == account.id).count() == 0
        remotes = github.list_repos(account.origin_account, account.origin_kind, account.include_forks)
        for remote in remotes:
            if cancelled(account.id):
                live = db.get(Account, account.id)
                if live:
                    live.status = "idle"
                    db.commit()
                break
            repo, created = _upsert_repo(db, account, remote)
            db.commit()
            db.refresh(repo)
            try:
                if first_account:
                    _baseline_repo(account, repo, remote)
                    db.commit()
                    continue

                if created:
                    repo.status = "syncing"
                    db.commit()
                    _open_new_repo(account, repo, remote)
                    _record_event(
                        db,
                        account,
                        "new-repo",
                        f"New repo {account.origin_account}/{repo.name} → {settings.dest_account}/{repo.name}",
                        repo=repo,
                    )
                    db.commit()
                    new_repos.append(repo)
                    continue

                remote_pushed = remote.get("pushed_at") or ""
                if repo.last_sha and not repo.pushed_at:
                    repo.pushed_at = remote_pushed
                    repo.status = "idle"
                    db.commit()
                    continue
                if repo.pushed_at and repo.pushed_at == remote_pushed:
                    repo.status = "idle"
                    db.commit()
                    continue

                repo.status = "syncing"
                db.commit()
                commits, _tip = _relay_new_commits(account, repo, remote)
                stored: list[Commit] = []
                for item in commits:
                    existing = (
                        db.query(Commit)
                        .filter(Commit.repo_id == repo.id, Commit.sha == item["sha"])
                        .first()
                    )
                    if existing:
                        continue
                    row = Commit(account_id=account.id, repo_id=repo.id, **item)
                    db.add(row)
                    stored.append(row)
                repo.commits_synced = (repo.commits_synced or 0) + len(stored)
                db.commit()
                for row in stored:
                    db.refresh(row)
                if stored:
                    commit_groups.append(
                        {"name": repo.name, "branch": repo.default_branch, "commits": stored}
                    )
                    stored_total += len(stored)
            except Exception as exc:  # noqa: BLE001
                repo.status = "error"
                repo.last_error = str(exc)
                repo.last_sync_at = utcnow()
                _record_event(db, account, "error", f"{repo.name} failed", str(exc), repo=repo)
                db.commit()
                errors.append(f"{repo.name}: {exc}")
                log.exception("repo %s/%s failed", account.origin_account, repo.name)

        live = db.get(Account, account.id)
        if not live:
            return {
                "ok": True,
                "first": first_account,
                "new_repos": new_repos,
                "commit_groups": commit_groups,
                "count": stored_total,
                "repo_count": len(remotes),
                "errors": errors,
            }
        account = live
        account.last_sync_at = utcnow()
        account.status = "error" if errors and not remotes else ("error" if errors and stored_total == 0 and not new_repos else "idle")
        if errors and (new_repos or stored_total):
            account.status = "idle"
            account.last_error = "\n".join(errors[:8])
        elif errors:
            account.status = "error"
            account.last_error = "\n".join(errors[:8])
        else:
            account.last_error = ""
        if first_account:
            _record_event(
                db,
                account,
                "tracking",
                f"Watching {len(remotes)} repo{'s' if len(remotes) != 1 else ''} on {account.origin_account}. Dest only gets new repos and new commits.",
            )
        elif stored_total:
            _record_event(db, account, "sync", f"Relayed {stored_total} commit{'s' if stored_total != 1 else ''}")
        db.commit()
        return {
            "ok": not (account.status == "error" and not new_repos and stored_total == 0),
            "first": first_account,
            "new_repos": new_repos,
            "commit_groups": commit_groups,
            "count": stored_total,
            "repo_count": len(remotes),
            "errors": errors,
        }
    except Exception as exc:  # noqa: BLE001
        live = db.get(Account, account.id)
        if not live:
            return {
                "ok": True,
                "first": first_account,
                "new_repos": [],
                "commit_groups": [],
                "count": 0,
                "repo_count": 0,
                "errors": [],
            }
        account = live
        account.status = "error"
        account.last_error = str(exc)
        account.last_sync_at = utcnow()
        _record_event(db, account, "error", "Account sync failed", str(exc))
        db.commit()
        log.exception("account %s failed", account.id)
        return {
            "ok": False,
            "first": first_account,
            "new_repos": [],
            "commit_groups": [],
            "count": 0,
            "repo_count": 0,
            "errors": [str(exc)],
        }


async def run_account(account_id: int) -> dict:
    if cancelled(account_id):
        clear_cancel(account_id)
        return {"ok": True, "count": 0}
    async with account_lock(account_id):
        if cancelled(account_id):
            clear_cancel(account_id)
            return {"ok": True, "count": 0}
        db = SessionLocal()
        try:
            account = db.get(Account, account_id)
            if not account:
                return {"ok": False, "error": "account not found"}
            await bus.publish("account", {"id": account.id, "status": "syncing"})
            result = await asyncio.to_thread(sync_account_now, db, account)
            account = db.get(Account, account_id)
            if not account:
                return {"ok": True, "count": 0}
            await bus.publish("account", {"id": account.id, "status": account.status})
            if not cancelled(account_id):
                await discord.notify_digest(account, result)
            if result.get("count") or result.get("new_repos"):
                await bus.publish("commits", {"account_id": account.id, "count": result.get("count", 0)})
            return {
                "ok": result.get("ok"),
                "error": "; ".join(result.get("errors") or []) or None,
                "count": result.get("count", 0),
            }
        finally:
            clear_cancel(account_id)
            db.close()


async def run_due_accounts() -> None:
    db = SessionLocal()
    try:
        ids = [row.id for row in db.query(Account).filter(Account.paused.is_(False)).all()]
    finally:
        db.close()
    for account_id in ids:
        try:
            await run_account(account_id)
        except Exception:
            log.exception("account %s crashed", account_id)


def wipe_account_clones(account_id: int) -> None:
    shutil.rmtree(settings.clones_dir / str(account_id), ignore_errors=True)


def wipe_orphan_clones(keep_ids: set[int]) -> None:
    root = settings.clones_dir
    if not root.exists():
        return
    keep = {str(i) for i in keep_ids}
    for path in root.iterdir():
        if path.is_dir() and path.name not in keep:
            shutil.rmtree(path, ignore_errors=True)
