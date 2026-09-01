from __future__ import annotations

import time
from datetime import datetime, timezone
from urllib.parse import quote, urlparse
import re

import httpx

from .config import settings
from .tokens import bucket_key, next_dest_token, token_hint

API = "https://api.github.com"


class GithubError(RuntimeError):
    pass


class GithubRateLimit(GithubError):
    def __init__(self, message: str, *, token: str = "", reset_at: float | None = None) -> None:
        super().__init__(message)
        self.token = token
        self.reset_at = reset_at


_buckets: dict[str, dict] = {}
_dest_known: set[str] = set()
_list_cache: dict[str, tuple[str, list[dict]]] = {}


def _state(key: str, *, authenticated: bool) -> dict:
    if key not in _buckets:
        _buckets[key] = {
            "until": 0.0,
            "remaining": 5000 if authenticated else 60,
            "hint": token_hint(key) if key not in {"public"} else "public",
        }
    return _buckets[key]


def _key_for_token(token: str) -> str:
    return bucket_key(token)


def is_blocked(token: str = "") -> bool:
    key = _key_for_token(token)
    return time.time() < _state(key, authenticated=bool(token.strip()))["until"]


def remaining(token: str = "") -> int:
    if token:
        key = _key_for_token(token)
        return int(_state(key, authenticated=bool(token.strip()))["remaining"])
    if not _buckets:
        return 5000 if settings.poll_token else 60
    return min(int(state["remaining"]) for state in _buckets.values())


def reset_at(token: str = "") -> float | None:
    if token:
        key = _key_for_token(token)
        state = _state(key, authenticated=bool(token.strip()))
        return state["until"] if time.time() < state["until"] else None
    blocked = [state["until"] for state in _buckets.values() if time.time() < state["until"]]
    return max(blocked) if blocked else None


def reset_iso(token: str = "") -> str | None:
    at = reset_at(token)
    if not at:
        return None
    return datetime.fromtimestamp(at, tz=timezone.utc).isoformat()


def poll_auth() -> str:
    return settings.poll_auth


def bucket_summaries(account_labels: dict[str, list[str]] | None = None) -> list[dict]:
    account_labels = account_labels or {}
    out: list[dict] = []
    keys = set(_buckets) | set(account_labels)
    if not keys:
        key = _key_for_token(settings.poll_token)
        keys = {key}
    for key in sorted(keys):
        authenticated = key != "public"
        state = _state(key, authenticated=authenticated)
        paused = time.time() < state["until"]
        out.append(
            {
                "key": key[:8],
                "hint": state.get("hint") or (key[:8] if key != "public" else "public"),
                "remaining": int(state["remaining"]),
                "paused_until": datetime.fromtimestamp(state["until"], tz=timezone.utc).isoformat()
                if paused
                else None,
                "accounts": account_labels.get(key, []),
            }
        )
    return out


def _check_budget(token: str) -> None:
    key = _key_for_token(token)
    if time.time() < _state(key, authenticated=bool(token.strip()))["until"]:
        reset = reset_at(token)
        raise GithubRateLimit(
            "GitHub rate limit — polling paused until reset",
            token=token,
            reset_at=reset,
        )


def _track(response: httpx.Response, token: str) -> None:
    key = _key_for_token(token)
    state = _state(key, authenticated=bool(token.strip()))
    if token.strip():
        state["hint"] = token_hint(token)
    rem = response.headers.get("x-ratelimit-remaining")
    reset = response.headers.get("x-ratelimit-reset")
    if rem is not None:
        try:
            state["remaining"] = int(rem)
        except ValueError:
            pass
    reset_ts = None
    if reset:
        try:
            reset_ts = float(reset)
        except ValueError:
            pass
    body = ""
    try:
        body = (response.text or "").lower()
    except Exception:
        body = ""
    limited = response.status_code == 403 and (
        "rate limit" in body or "secondary rate" in body or rem == "0"
    )
    if limited:
        retry = response.headers.get("retry-after")
        if retry and str(retry).isdigit():
            state["until"] = time.time() + int(retry) + 3
        elif reset_ts:
            state["until"] = reset_ts + 3
        else:
            state["until"] = time.time() + 120
        raise GithubRateLimit(
            "GitHub rate limit — polling paused until reset",
            token=token,
            reset_at=state["until"],
        )
    if int(state["remaining"]) == 0 and reset_ts:
        state["until"] = max(float(state["until"]), reset_ts)


def _raise_for_status(response: httpx.Response, token: str) -> None:
    _track(response, token)
    if response.status_code >= 400:
        raise GithubError(_err(response))


def parse_account(value: str) -> str:
    value = (value or "").strip().strip("/")
    if not value:
        return ""
    if value.startswith("git@github.com:"):
        return value.split(":", 1)[1].split("/")[0]
    if "github.com" in value or value.startswith("http"):
        try:
            parsed = urlparse(value if "://" in value else f"https://{value}")
            part = parsed.path.strip("/").split("/")[0]
            return part
        except ValueError:
            return value
    return re.sub(r"[^A-Za-z0-9_.-]", "", value.split("/")[0])


def origin_https(account: str, repo: str) -> str:
    return f"https://github.com/{account}/{repo}.git"


def dest_https(repo: str) -> str:
    return f"https://github.com/{settings.dest_account}/{repo}.git"


def _headers(token: str | None = None) -> dict[str, str]:
    token = (token if token is not None else settings.poll_token).strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "relay-tracker",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _next_link(link: str | None) -> str | None:
    if not link:
        return None
    for part in link.split(","):
        if 'rel="next"' in part:
            match = re.search(r"<([^>]+)>", part)
            if match:
                return match.group(1)
    return None


def _get_json(path: str, token: str | None = None) -> tuple[object, httpx.Headers]:
    token = (token if token is not None else settings.poll_token).strip()
    _check_budget(token)
    with httpx.Client(timeout=30, headers=_headers(token), follow_redirects=True) as client:
        response = client.get(path if path.startswith("http") else f"{API}{path}")
        _raise_for_status(response, token)
        return response.json(), response.headers


def _err(response: httpx.Response) -> str:
    try:
        body = response.json()
        msg = body.get("message") or response.text
    except Exception:
        msg = response.text
    return f"GitHub {response.status_code}: {str(msg)[:400]}"


def account_profile(login: str, token: str | None = None) -> dict:
    data, _ = _get_json(f"/users/{login}", token)
    if not isinstance(data, dict):
        raise GithubError("unexpected GitHub response")
    return data


_dest_identity: tuple[str, str] | None = None


def dest_identity() -> tuple[str, str]:
    global _dest_identity
    login = settings.dest_account
    if not login:
        raise GithubError("DEST_GITHUB_ACCOUNT is not set")
    if _dest_identity and _dest_identity[1].endswith(f"{login}@users.noreply.github.com"):
        return _dest_identity
    name = login
    email = f"{login}@users.noreply.github.com"
    try:
        profile, _ = _get_json(f"/users/{login}", next_dest_token() or settings.dest_token or None)
        if isinstance(profile, dict):
            name = (profile.get("name") or profile.get("login") or login).strip() or login
            user_id = profile.get("id")
            if user_id:
                email = f"{user_id}+{login}@users.noreply.github.com"
    except Exception:  # noqa: BLE001
        pass
    _dest_identity = (name, email)
    return _dest_identity


def list_repos(login: str, kind: str, include_forks: bool, token: str | None = None) -> list[dict]:
    token = (token if token is not None else settings.poll_token).strip()
    _check_budget(token)
    path = f"/orgs/{login}/repos" if kind == "Organization" else f"/users/{login}/repos"
    url = f"{API}{path}?per_page=100&type=all&sort=updated"
    cache_key = f"{bucket_key(token)}:{login}:{kind}:{include_forks}"
    rows: list[dict] = []
    headers = _headers(token)
    cached = _list_cache.get(cache_key)
    if cached:
        headers["If-None-Match"] = cached[0]
    etag = ""
    with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as client:
        first = True
        while url:
            _check_budget(token)
            response = client.get(url)
            if first and response.status_code == 304 and cached:
                _track(response, token)
                return cached[1]
            _raise_for_status(response, token)
            chunk = response.json()
            if not isinstance(chunk, list):
                raise GithubError("unexpected GitHub repo list")
            rows.extend(chunk)
            if first:
                etag = response.headers.get("etag") or ""
            first = False
            url = _next_link(response.headers.get("link"))
    out = []
    for item in rows:
        if item.get("archived"):
            continue
        if item.get("fork") and not include_forks:
            continue
        name = item.get("name") or ""
        if not name:
            continue
        out.append(
            {
                "name": name,
                "private": bool(item.get("private")),
                "fork": bool(item.get("fork")),
                "default_branch": item.get("default_branch") or "main",
                "html_url": item.get("html_url") or origin_https(login, name),
                "clone_url": item.get("clone_url") or origin_https(login, name),
                "description": (item.get("description") or "")[:180],
                "pushed_at": item.get("pushed_at") or "",
                "empty": int(item.get("size") or 0) == 0,
            }
        )
    if etag:
        _list_cache[cache_key] = (etag, out)
    return out


def tip_sha(owner: str, name: str, branch: str, token: str | None = None) -> str:
    token = (token if token is not None else settings.poll_token).strip()
    _check_budget(token)
    ref = quote(branch or "main", safe="")
    with httpx.Client(timeout=30, headers=_headers(token), follow_redirects=True) as client:
        response = client.get(f"{API}/repos/{owner}/{name}/commits/{ref}")
        if response.status_code in {404, 409}:
            _track(response, token)
            return ""
        _raise_for_status(response, token)
        data = response.json()
        if isinstance(data, dict):
            return str(data.get("sha") or "")
        return ""


def _dest_api_token() -> str:
    return next_dest_token() or settings.dest_token


def ensure_dest_repo(name: str, private: bool, description: str = "") -> None:
    token = _dest_api_token()
    if not token:
        raise GithubError("DEST_GITHUB_TOKEN is not set")
    if not settings.dest_account:
        raise GithubError("DEST_GITHUB_ACCOUNT is not set")
    if name in _dest_known:
        return
    _check_budget(token)
    payload = {
        "name": name,
        "private": private,
        "has_issues": False,
        "has_projects": False,
        "has_wiki": False,
        "auto_init": False,
    }
    if description:
        payload["description"] = description
    with httpx.Client(timeout=30, headers=_headers(token), follow_redirects=True) as client:
        existing = client.get(f"{API}/repos/{settings.dest_account}/{name}")
        if existing.status_code == 200:
            _track(existing, token)
            _dest_known.add(name)
            current = ((existing.json() or {}).get("description") or "").strip()
            if current.startswith("Relay of "):
                patched = client.patch(
                    f"{API}/repos/{settings.dest_account}/{name}",
                    json={"description": description},
                )
                _track(patched, token)
            return
        if existing.status_code not in {404, 301}:
            _raise_for_status(existing, token)
        else:
            _track(existing, token)
        profile = client.get(f"{API}/users/{settings.dest_account}")
        _raise_for_status(profile, token)
        kind = (profile.json() or {}).get("type") or "User"
        url = f"{API}/orgs/{settings.dest_account}/repos" if kind == "Organization" else f"{API}/user/repos"
        created = client.post(url, json=payload)
        if created.status_code in {201, 202}:
            _track(created, token)
            _dest_known.add(name)
            return
        if created.status_code == 422:
            _track(created, token)
            body = created.json() if created.headers.get("content-type", "").startswith("application/json") else {}
            errors = body.get("errors") or []
            if any("already exists" in str(e).lower() for e in errors) or "already exists" in str(body).lower():
                _dest_known.add(name)
                return
        _raise_for_status(created, token)


def scrub_relay_descriptions() -> None:
    token = _dest_api_token()
    if not token or not settings.dest_account:
        return
    if is_blocked(token):
        return
    with httpx.Client(timeout=30, headers=_headers(token), follow_redirects=True) as client:
        profile = client.get(f"{API}/users/{settings.dest_account}")
        _raise_for_status(profile, token)
        kind = (profile.json() or {}).get("type") or "User"
        url = (
            f"{API}/orgs/{settings.dest_account}/repos?per_page=100&type=all"
            if kind == "Organization"
            else f"{API}/user/repos?per_page=100&affiliation=owner"
        )
        while url:
            _check_budget(token)
            response = client.get(url)
            _raise_for_status(response, token)
            chunk = response.json()
            if not isinstance(chunk, list):
                break
            for item in chunk:
                desc = (item.get("description") or "").strip()
                name = item.get("name") or ""
                if name:
                    _dest_known.add(name)
                if name and desc.startswith("Relay of "):
                    patched = client.patch(
                        f"{API}/repos/{settings.dest_account}/{name}",
                        json={"description": ""},
                    )
                    _track(patched, token)
            url = _next_link(response.headers.get("link"))
