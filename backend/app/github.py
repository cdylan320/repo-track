from __future__ import annotations

import re
from urllib.parse import quote, urlparse

import httpx

from .config import settings

API = "https://api.github.com"


class GithubError(RuntimeError):
    pass


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
    token = (token or settings.api_token).strip()
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
    with httpx.Client(timeout=30, headers=_headers(token), follow_redirects=True) as client:
        response = client.get(path if path.startswith("http") else f"{API}{path}")
        if response.status_code >= 400:
            raise GithubError(_err(response))
        return response.json(), response.headers


def _err(response: httpx.Response) -> str:
    try:
        body = response.json()
        msg = body.get("message") or response.text
    except Exception:
        msg = response.text
    return f"GitHub {response.status_code}: {str(msg)[:400]}"


def account_profile(login: str) -> dict:
    data, _ = _get_json(f"/users/{login}")
    if not isinstance(data, dict):
        raise GithubError("unexpected GitHub response")
    return data


def list_repos(login: str, kind: str, include_forks: bool) -> list[dict]:
    path = f"/orgs/{login}/repos" if kind == "Organization" else f"/users/{login}/repos"
    url = f"{API}{path}?per_page=100&type=all&sort=updated"
    rows: list[dict] = []
    with httpx.Client(timeout=30, headers=_headers(), follow_redirects=True) as client:
        while url:
            response = client.get(url)
            if response.status_code >= 400:
                raise GithubError(_err(response))
            chunk = response.json()
            if not isinstance(chunk, list):
                raise GithubError("unexpected GitHub repo list")
            rows.extend(chunk)
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
    return out


def tip_sha(owner: str, name: str, branch: str) -> str:
    ref = quote(branch or "main", safe="")
    with httpx.Client(timeout=30, headers=_headers(), follow_redirects=True) as client:
        response = client.get(f"{API}/repos/{owner}/{name}/commits/{ref}")
        if response.status_code in {404, 409}:
            return ""
        if response.status_code >= 400:
            raise GithubError(_err(response))
        data = response.json()
        if isinstance(data, dict):
            return str(data.get("sha") or "")
        return ""


def ensure_dest_repo(name: str, private: bool, description: str) -> None:
    if not settings.dest_token:
        raise GithubError("DEST_GITHUB_TOKEN is not set")
    if not settings.dest_account:
        raise GithubError("DEST_GITHUB_ACCOUNT is not set")
    payload = {
        "name": name,
        "private": private,
        "description": description or f"Relay of {name}",
        "has_issues": False,
        "has_projects": False,
        "has_wiki": False,
        "auto_init": False,
    }
    with httpx.Client(timeout=30, headers=_headers(settings.dest_token), follow_redirects=True) as client:
        existing = client.get(f"{API}/repos/{settings.dest_account}/{name}")
        if existing.status_code == 200:
            return
        profile = client.get(f"{API}/users/{settings.dest_account}")
        kind = "User"
        if profile.status_code == 200:
            kind = (profile.json() or {}).get("type") or "User"
        url = f"{API}/orgs/{settings.dest_account}/repos" if kind == "Organization" else f"{API}/user/repos"
        created = client.post(url, json=payload)
        if created.status_code in {201, 202}:
            return
        if created.status_code == 422:
            body = created.json() if created.headers.get("content-type", "").startswith("application/json") else {}
            errors = body.get("errors") or []
            if any("already exists" in str(e).lower() for e in errors) or "already exists" in str(body).lower():
                return
        raise GithubError(_err(created))
