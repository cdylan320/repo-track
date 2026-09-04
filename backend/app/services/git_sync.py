from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from .. import github
from ..config import settings
from ..database import SessionLocal
from ..events import bus
from ..gitutil import inject_token
from ..models import Account, Commit, Event, Repo, utcnow
from ..tokens import next_dest_token, poll_token_for_account, token_hint
from . import discord, rate_alerts

log = logging.getLogger("relay.sync")

#: The dest repo carries exactly one commit, and this is its message.
DEST_COMMIT_MESSAGE = "initial commit"

_locks: dict[int, asyncio.Lock] = {}
_cancel: set[int] = set()
_running = False
_next_tick: datetime | None = None
_dest_normalized = False


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


def _run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    child_env = os.environ.copy()
    child_env["GIT_TERMINAL_PROMPT"] = "0"
    child_env["GIT_ASKPASS"] = "echo"
    child_env.update(env or {})
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=settings.git_timeout_seconds,
        env=child_env,
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
    poll_token = poll_token_for_account(account)
    origin_git = settings.origin_token or poll_token
    origin = inject_token(repo.origin_url, origin_git)
    dest = inject_token(repo.dest_url, next_dest_token() or settings.dest_token)

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


def _parse_authored(date_raw: str) -> datetime | None:
    """Git's %aI carries the author's own UTC offset; store the instant in UTC.

    SQLite drops tzinfo on write, so a `13:12-04:00` value would come back as a naive
    13:12 and be read as UTC — four hours in the past, which the feed then reports as
    a late relay. Converting here keeps the stored wall clock UTC like every other column.
    """
    if not date_raw:
        return None
    try:
        parsed = datetime.fromisoformat(date_raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
        sha, _origin_message, name, email, date_raw = parts[:5]
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
        authored_at = _parse_authored(date_raw)
        commits.append(
            {
                "sha": sha,
                "short_sha": sha[:7],
                # What Relay actually pushed, not what origin wrote — dest only ever
                # carries the one squashed commit, so the feed reports that message.
                "message": DEST_COMMIT_MESSAGE,
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
    if not _origin_tip(repo):
        raise RuntimeError(f"branch '{branch}' not found on origin")
    code, _, err = _git(repo, ["checkout", "-B", f"relay/{branch}", f"origin/{branch}"])
    if code == 0:
        return
    for fallback in (branch, "main", "master"):
        if not fallback:
            continue
        code, _, err = _git(repo, ["checkout", "-B", f"relay/{fallback}", f"origin/{fallback}"])
        if code == 0:
            repo.default_branch = fallback
            return
    raise RuntimeError(_clean_err(err) or f"branch '{branch}' not found on origin")


def _squash_dest_commit(repo: Repo, dest_ref: str) -> None:
    """Point dest_ref at a single root commit holding origin's current tree.

    The dest repo carries one commit, always titled `initial commit`, no matter how many
    commits origin has: origin's history and messages never reach it. The commit takes the
    origin tip's author date so the same tree always yields the same dest SHA, and it is
    authored as the dest account.
    """
    name, email = github.dest_identity()

    code, tree, err = _git(repo, ["rev-parse", "HEAD^{tree}"])
    if code != 0 or not tree:
        raise RuntimeError(_clean_err(err) or "could not read the origin tree")

    code, when, err = _git(repo, ["log", "-1", "--pretty=format:%aI", "HEAD"])
    if code != 0 or not when:
        raise RuntimeError(_clean_err(err) or "could not read the origin tip date")

    env = {
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
        "GIT_COMMITTER_DATE": when,
    }
    code, sha, err = _run(
        ["git", "commit-tree", tree, "-m", DEST_COMMIT_MESSAGE],
        cwd=clone_dir(repo.account_id, repo.name),
        env=env,
    )
    if code != 0 or not sha:
        raise RuntimeError(_clean_err(err) or "could not build the dest commit")

    code, _, err = _git(repo, ["update-ref", dest_ref, sha])
    if code != 0:
        raise RuntimeError(_clean_err(err) or "could not update the dest ref")


def _push_lock_error(err: str) -> bool:
    low = (err or "").lower()
    return "cannot lock ref" in low or "reference already exists" in low


def _push_dest(repo: Repo) -> None:
    """Replace the dest branch with the single `initial commit` for origin's current tree.

    Always a force push: each sync builds a fresh root commit, so it never fast-forwards
    over the one already there, so an account's ff-only sync_mode does not apply here.
    """
    branch = repo.default_branch or "main"
    dest_ref = f"refs/heads/relay-dest/{branch}"
    _squash_dest_commit(repo, dest_ref)
    refspec = f"{dest_ref}:refs/heads/{branch}"
    delays = (0.0, 1.0, 2.5)
    last_err = ""
    for attempt, delay in enumerate(delays):
        if delay:
            time.sleep(delay)
        code, _, err = _git(repo, ["push", "--force", "dest", refspec])
        last_err = err
        if code == 0:
            repo.reauthored = True
            return
        if _push_lock_error(err) and attempt < len(delays) - 1:
            log.warning(
                "dest push lock on %s/%s (retry %s/%s)",
                repo.account_id,
                repo.name,
                attempt + 1,
                len(delays),
            )
            continue
        break
    raise RuntimeError(_clean_err(last_err) or "git push dest failed")


def _is_sha(value: str) -> bool:
    value = (value or "").strip()
    return len(value) >= 7 and all(c in "0123456789abcdefABCDEF" for c in value)


def _origin_has_commits(remote: dict) -> bool:
    return bool((remote.get("pushed_at") or "").strip())


def _is_empty_origin_error(message: str) -> bool:
    low = (message or "").lower()
    return (
        "not a commit" in low
        or "cannot be created from it" in low
        or "branch '" in low and "not found on origin" in low
    )


def _is_push_lock_error(message: str) -> bool:
    return _push_lock_error(message)


def _origin_tip(repo: Repo) -> str:
    """Return origin tip SHA if default branch exists, else try main/master."""
    branch = repo.default_branch or "main"
    for candidate in (branch, "main", "master"):
        code, tip, _ = _git(repo, ["rev-parse", f"origin/{candidate}"])
        if code == 0 and tip:
            if candidate != repo.default_branch:
                repo.default_branch = candidate
            return tip
    return ""


def _mark_origin_waiting(repo: Repo, remote: dict, account: Account) -> None:
    """Origin repo exists but has no commits yet — skip quietly until it gets content."""
    repo.last_sha = ""
    repo.pushed_at = remote.get("pushed_at") or repo.pushed_at
    repo.mirrored = True
    repo.reauthored = True
    repo.status = "idle"
    repo.last_error = ""
    repo.last_sync_at = utcnow()
    log.info(
        "waiting for commits — %s/%s has no branch to mirror yet",
        account.origin_account,
        repo.name,
    )


def _baseline_repo(account: Account, repo: Repo, remote: dict) -> None:
    poll_token = poll_token_for_account(account)
    sha = github.tip_sha(
        account.origin_account,
        repo.name,
        remote["default_branch"] or repo.default_branch,
        token=poll_token,
    )
    repo.last_sha = sha
    repo.pushed_at = remote.get("pushed_at") or repo.pushed_at
    repo.default_branch = remote.get("default_branch") or repo.default_branch
    repo.mirrored = False
    repo.status = "idle"
    repo.last_error = ""
    repo.last_sync_at = utcnow()


def _open_new_repo(account: Account, repo: Repo, remote: dict) -> str:
    if not _origin_has_commits(remote):
        _mark_origin_waiting(repo, remote, account)
        return ""
    _ensure_clone(account, repo)
    code, _, err = _git(repo, ["fetch", "origin", "--prune"])
    if code != 0:
        raise RuntimeError(_clean_err(err) or "git fetch origin failed")
    tip = _origin_tip(repo)
    if not tip:
        _mark_origin_waiting(repo, remote, account)
        return ""
    github.ensure_dest_repo(repo.name, remote.get("description") or "")
    repo.mirrored = True
    repo.pushed_at = remote.get("pushed_at") or ""
    _checkout_branch(repo)
    _push_dest(repo)
    repo.last_sha = tip
    repo.status = "idle"
    repo.last_error = ""
    repo.last_sync_at = utcnow()
    return tip


def _reauthor_dest(account: Account, repo: Repo, remote: dict) -> None:
    """Re-push an already-mirrored repo so its dest history carries dest authorship."""
    if not _origin_has_commits(remote):
        _mark_origin_waiting(repo, remote, account)
        return
    github.ensure_dest_repo(repo.name, remote.get("description") or "")
    _ensure_clone(account, repo)
    code, _, err = _git(repo, ["fetch", "origin", "--prune"])
    if code != 0:
        raise RuntimeError(_clean_err(err) or "git fetch origin failed")
    tip = _origin_tip(repo)
    if not tip:
        _mark_origin_waiting(repo, remote, account)
        return
    _checkout_branch(repo)
    _push_dest(repo)
    repo.reauthored = True
    repo.last_sha = tip
    repo.status = "idle"
    repo.last_error = ""
    repo.last_sync_at = utcnow()


def _relay_new_commits(account: Account, repo: Repo, remote: dict) -> tuple[list[dict], str]:
    if not _origin_has_commits(remote):
        _mark_origin_waiting(repo, remote, account)
        return [], ""
    github.ensure_dest_repo(repo.name, remote.get("description") or "")
    _ensure_clone(account, repo)
    code, _, err = _git(repo, ["fetch", "origin", "--prune"])
    if code != 0:
        raise RuntimeError(_clean_err(err) or "git fetch origin failed")
    tip = _origin_tip(repo)
    if not tip:
        _mark_origin_waiting(repo, remote, account)
        return [], ""
    _checkout_branch(repo)
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
    _push_dest(repo)
    repo.mirrored = True
    repo.last_sha = tip
    repo.pushed_at = remote.get("pushed_at") or repo.pushed_at
    repo.status = "idle"
    repo.last_error = ""
    repo.last_sync_at = utcnow()
    return commits, tip


def repair_authored_dates(db: Session) -> int:
    """Re-read author dates from the local clones for rows saved with the old tz bug.

    Commits stored before %aI was normalised kept the author's local wall clock, so the
    feed showed them hours in the past. Repos without a clone on disk are left alone.
    """
    fixed = 0
    repos = db.query(Repo).join(Commit, Commit.repo_id == Repo.id).distinct().all()
    for repo in repos:
        folder = settings.clones_dir / str(repo.account_id) / repo.name
        if not (folder / ".git").exists():
            continue
        code, out, _ = _run(["git", "log", "--all", "--pretty=format:%H %aI"], cwd=folder)
        if code != 0 or not out.strip():
            continue
        dates = {}
        for line in out.splitlines():
            sha, _, iso = line.partition(" ")
            parsed = _parse_authored(iso.strip())
            if sha and parsed:
                dates[sha] = parsed
        for commit in db.query(Commit).filter(Commit.repo_id == repo.id).all():
            correct = dates.get(commit.sha)
            if not correct:
                continue
            current = commit.authored_at
            if current is not None and current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            if current != correct:
                commit.authored_at = correct
                fixed += 1
    if fixed:
        db.commit()
    return fixed


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
    global _dest_normalized
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
        if not _dest_normalized:
            try:
                managed = {name for (name,) in db.query(Repo.name).distinct().all()}
                github.normalize_dest_repos(managed)
                _dest_normalized = True
            except Exception:
                log.exception("could not normalize dest repos")
        first_account = db.query(Repo).filter(Repo.account_id == account.id).count() == 0
        poll_token = poll_token_for_account(account)
        remotes = github.list_repos(
            account.origin_account,
            account.origin_kind,
            account.include_forks,
            token=poll_token,
        )
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
                    tip = _open_new_repo(account, repo, remote)
                    stored: list[Commit] = []
                    if tip:
                        for item in _log_range(repo, ["-n", "20", "HEAD"]):
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
                        _record_event(
                            db,
                            account,
                            "new-repo",
                            f"New repo {account.origin_account}/{repo.name} → {settings.dest_account}/{repo.name}",
                            repo=repo,
                        )
                        new_repos.append(repo)
                    db.commit()
                    for row in stored:
                        db.refresh(row)
                    if stored:
                        commit_groups.append(
                            {"name": repo.name, "branch": repo.default_branch, "commits": stored}
                        )
                        stored_total += len(stored)
                    continue

                remote_pushed = remote.get("pushed_at") or ""
                # Origin was empty when first seen; retry only when pushed_at moves (first real commit).
                if repo.mirrored and not repo.last_sha and repo.reauthored:
                    if remote_pushed and remote_pushed != repo.pushed_at:
                        repo.status = "syncing"
                        db.commit()
                        tip = _open_new_repo(account, repo, remote)
                        if tip:
                            stored: list[Commit] = []
                            for item in _log_range(repo, ["-n", "20", "HEAD"]):
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
                    else:
                        repo.status = "idle"
                        db.commit()
                    continue
                # Dest shell exists but content never pushed (e.g. false empty detection).
                if repo.mirrored and not repo.last_sha and remote_pushed and not repo.reauthored:
                    repo.status = "syncing"
                    db.commit()
                    tip = _open_new_repo(account, repo, remote)
                    if tip:
                        stored: list[Commit] = []
                        for item in _log_range(repo, ["-n", "20", "HEAD"]):
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
                    db.commit()
                    continue
                if repo.mirrored and not repo.reauthored:
                    if not _origin_has_commits(remote):
                        _mark_origin_waiting(repo, remote, account)
                        db.commit()
                        continue
                    repo.status = "syncing"
                    db.commit()
                    _reauthor_dest(account, repo, remote)
                    if repo.reauthored and not repo.last_sha:
                        db.commit()
                        continue
                    repo.pushed_at = remote_pushed or repo.pushed_at
                    _record_event(
                        db,
                        account,
                        "sync",
                        f"Re-authored {repo.name} as {settings.dest_account}",
                        repo=repo,
                    )
                    db.commit()
                    continue
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
            except github.GithubRateLimit:
                raise
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                if _is_empty_origin_error(msg):
                    _mark_origin_waiting(repo, remote, account)
                    db.commit()
                    log.info(
                        "empty origin skipped — %s/%s",
                        account.origin_account,
                        repo.name,
                    )
                    continue
                if github.is_transient_error(exc) or _is_push_lock_error(msg):
                    repo.status = "idle"
                    repo.last_error = ""
                    repo.last_sync_at = utcnow()
                    db.commit()
                    log.warning(
                        "transient error — %s/%s: %s",
                        account.origin_account,
                        repo.name,
                        exc,
                    )
                    continue
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
    except github.GithubRateLimit as exc:
        live = db.get(Account, account.id)
        rate_token = exc.token or poll_token_for_account(account)
        resume = github.reset_iso(rate_token)
        if live:
            live.status = "idle"
            live.last_error = "GitHub rate limit — polling paused until reset"
            _record_event(
                db,
                live,
                "rate-limit",
                f"GitHub rate limit — {live.origin_account} polling paused",
                f"Token {token_hint(rate_token)} · resumes {resume or 'unknown'}",
            )
            db.commit()
        rate_alerts.log_rate_limit(account.origin_account, rate_token)
        return {
            "ok": True,
            "first": first_account,
            "new_repos": [],
            "commit_groups": [],
            "count": 0,
            "repo_count": 0,
            "errors": [],
            "rate_limited": True,
            "rate_token": rate_token,
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
        if github.is_transient_error(exc) or _is_push_lock_error(str(exc)):
            account.status = "idle"
            account.last_error = ""
            account.last_sync_at = utcnow()
            db.commit()
            log.warning(
                "transient GitHub/network error for %s (will retry next poll): %s",
                account.origin_account,
                exc,
            )
            return {
                "ok": True,
                "first": first_account,
                "new_repos": [],
                "commit_groups": [],
                "count": 0,
                "repo_count": 0,
                "errors": [],
                "transient": True,
            }
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
            if result.get("rate_limited"):
                rate_token = result.get("rate_token") or poll_token_for_account(account)
                db2 = SessionLocal()
                try:
                    rows = db2.query(Account).order_by(Account.id.asc()).all()
                    buckets, limited = rate_alerts.bucket_payload(rows)
                finally:
                    db2.close()
                await rate_alerts.emit_rate_limit(
                    account_id=account.id,
                    origin=account.origin_account,
                    token=rate_token,
                    github_buckets=buckets,
                    rate_limited_count=limited,
                )
            elif not cancelled(account_id) and not result.get("transient"):
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
        ids = [row.id for row in db.query(Account).filter(Account.paused.is_(False)).order_by(Account.id.asc()).all()]
    finally:
        db.close()
    if not ids:
        return
    results = await asyncio.gather(*[run_account(account_id) for account_id in ids], return_exceptions=True)
    for account_id, result in zip(ids, results):
        if isinstance(result, github.GithubRateLimit):
            continue
        if isinstance(result, Exception):
            log.error("account %s crashed", account_id, exc_info=result)


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
