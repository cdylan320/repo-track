from __future__ import annotations

import httpx

from .. import github
from ..config import settings
from ..tokens import token_hint

SIGNAL = 0xC8F24A
FAULT = 0xFF6B5A
WARN = 0xFFC45A


async def notify_rate_limit(origin: str, token: str, *, resume: str | None = None) -> tuple[bool, str]:
    if not settings.discord_webhook_url.strip():
        return False, "not configured"
    remaining = github.remaining(token)
    hint = token_hint(token) or "token"
    resume_at = resume or github.reset_iso(token) or "next hour"
    return await send_discord(
        {
            "username": "Relay",
            "embeds": [
                {
                    "title": "GitHub rate limit — polling paused",
                    "description": (
                        f"**Now** — polling `{origin}` is blocked.\n"
                        f"Token `{hint}` · **{remaining}** calls left · resumes ~{resume_at}"
                    ),
                    "color": WARN,
                    "footer": {"text": "Relay · live rate-limit alert"},
                }
            ],
        }
    )


def webhook_hint(url: str) -> str:
    if not url:
        return ""
    if len(url) < 28:
        return "••••"
    return url[:32] + "…" + url[-6:]


async def send_discord(payload: dict) -> tuple[bool, str]:
    url = settings.discord_webhook_url.strip()
    if not url:
        return False, "DISCORD_WEBHOOK_URL is not set"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(url, json=payload)
        if response.status_code >= 300:
            return False, f"Discord returned {response.status_code}: {response.text[:240]}"
    return True, "sent"


def _subject(message: str) -> str:
    return (message or "—").split("\n", 1)[0][:72]


def _is_quiet_repo_error(message: str) -> bool:
    low = (message or "").lower()
    return (
        "not a commit" in low
        or "cannot be created from it" in low
        or ("branch" in low and "not found on origin" in low)
    )


def _is_transient_error_message(message: str) -> bool:
    return github.is_transient_error(RuntimeError(message))


def _is_push_lock_error_message(message: str) -> bool:
    low = (message or "").lower()
    return "cannot lock ref" in low or "reference already exists" in low


def _files_line(commit) -> str:
    names = (getattr(commit, "files_list", "") or "").split(", ")
    names = [n for n in names if n]
    shown = names[:5]
    extra = len(names) - len(shown)
    bits = "  ".join(f"`{n}`" for n in shown)
    if extra > 0:
        bits += f"  +{extra}"
    plus = getattr(commit, "insertions", 0) or 0
    minus = getattr(commit, "deletions", 0) or 0
    stats = f"+{plus} −{minus}"
    files_n = getattr(commit, "files_changed", 0) or len(names)
    return f"{files_n} file{'s' if files_n != 1 else ''} · {stats}" + (f"\n{bits}" if bits else "")


def _commit_block(commit) -> str:
    sha = getattr(commit, "short_sha", "") or (getattr(commit, "sha", "")[:7])
    author = getattr(commit, "author_name", "") or "unknown"
    return f"`{sha}`  {_subject(commit.message)}\n{author} · {_files_line(commit)}"


async def notify_digest(account, result: dict) -> tuple[bool, str]:
    if not settings.discord_webhook_url.strip():
        return False, "not configured"

    dest = settings.dest_account or "dest"
    origin = account.origin_account
    first = bool(result.get("first"))
    new_repos = result.get("new_repos") or []
    commit_groups: list = result.get("commit_groups") or []
    errors = result.get("errors") or []
    if result.get("transient"):
        return True, "transient quiet"
    if errors and all("rate limit" in str(e).lower() for e in errors):
        return True, "rate-limit folded"
    if errors and all(_is_quiet_repo_error(str(e)) for e in errors):
        return True, "empty-repo quiet"
    if errors and all(
        _is_transient_error_message(str(e)) or _is_push_lock_error_message(str(e)) for e in errors
    ):
        return True, "transient quiet"
    repo_count = result.get("repo_count") or 0

    if first and not errors:
        return await send_discord(
            {
                "username": "Relay",
                "embeds": [
                    {
                        "title": f"{origin}  →  {dest}",
                        "description": (
                            f"Baseline set. Watching **{repo_count}** repo{'s' if repo_count != 1 else ''} on `{origin}`.\n"
                            f"Nothing is copied to `{dest}` until a **new repo** appears or a repo gets a **new commit**."
                        ),
                        "color": SIGNAL,
                        "footer": {"text": "Relay · account track"},
                    }
                ],
            }
        )

    if not new_repos and not commit_groups and not errors:
        return True, "quiet"

    if errors and not new_repos and not commit_groups:
        return await send_discord(
            {
                "username": "Relay",
                "embeds": [
                    {
                        "title": f"{origin}  →  {dest}",
                        "description": "Sync hit a fault.",
                        "color": FAULT,
                        "fields": [{"name": "Errors", "value": "\n".join(f"`{e}`" for e in errors[:6])[:1000]}],
                        "footer": {"text": "Relay"},
                    }
                ],
            }
        )

    commit_total = sum(len(g.get("commits") or []) for g in commit_groups)
    parts = []
    if new_repos:
        parts.append(f"**{len(new_repos)}** new repo{'s' if len(new_repos) != 1 else ''}")
    if commit_total:
        parts.append(f"**{commit_total}** commit{'s' if commit_total != 1 else ''}")
    headline = " · ".join(parts) or "update"

    fields = []
    if new_repos:
        lines = []
        for repo in new_repos[:8]:
            origin_vis = "private" if repo.private else "public"
            lines.append(
                f"`{origin}/{repo.name}` ({origin_vis})  →  `{dest}/{repo.name}` (private)"
                f"  ·  `{repo.default_branch}`"
            )
        if len(new_repos) > 8:
            lines.append(f"…{len(new_repos) - 8} more")
        fields.append({"name": "New on dest", "value": "\n".join(lines)[:1024]})

    shown = 0
    for group in commit_groups:
        if shown >= 8:
            break
        name = group.get("name") or "repo"
        branch = group.get("branch") or "main"
        commits = group.get("commits") or []
        blocks = [_commit_block(c) for c in commits[:4]]
        if len(commits) > 4:
            blocks.append(f"…{len(commits) - 4} more")
        fields.append({"name": f"{name} · {branch}", "value": "\n\n".join(blocks)[:1024]})
        shown += 1
    leftover = len(commit_groups) - shown
    if leftover > 0:
        fields.append({"name": "Also", "value": f"{leftover} more repo{'s' if leftover != 1 else ''} updated"})

    if errors:
        fields.append({"name": "Faults", "value": "\n".join(f"`{e}`" for e in errors[:4])[:1024]})

    return await send_discord(
        {
            "username": "Relay",
            "embeds": [
                {
                    "title": f"{origin}  →  {dest}",
                    "description": headline,
                    "color": FAULT if errors and not commit_groups else SIGNAL,
                    "fields": fields[:25],
                    "footer": {"text": "Relay · only what moved"},
                }
            ],
        }
    )


async def notify_test() -> tuple[bool, str]:
    dest = settings.dest_account or "dest-account"
    return await send_discord(
        {
            "username": "Relay",
            "embeds": [
                {
                    "title": "Webhook connected",
                    "description": (
                        f"Mirrors land on **`{dest}`**.\n"
                        "You’ll get one note when origin creates a **new repo** or anyone **pushes a commit** — "
                        "not a clone of everything that already exists."
                    ),
                    "color": SIGNAL,
                    "footer": {"text": "Relay"},
                }
            ],
        }
    )
