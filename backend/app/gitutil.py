from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse


def repo_label(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return "unknown"
    if url.startswith("git@"):
        match = re.match(r"git@[^:]+:(.+?)(?:\.git)?$", url)
        if match:
            return match.group(1).strip("/")
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return path or url


def origin_host(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("git@"):
        match = re.match(r"git@([^:]+):", url)
        return match.group(1) if match else "git"
    parsed = urlparse(url)
    return parsed.hostname or "git"


def inject_token(url: str, token: str | None) -> str:
    if not token:
        return url
    if url.startswith("git@") or url.startswith("ssh://") or url.startswith("file://"):
        return url
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return url
    host = parsed.hostname or ""
    user = "x-access-token" if "github.com" in host else "oauth2"
    netloc = f"{user}:{token}@{host}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


def web_commit_url(url: str, sha: str) -> str:
    label = repo_label(url)
    host = origin_host(url)
    if "github.com" in host:
        return f"https://github.com/{label}/commit/{sha}"
    if "gitlab" in host:
        return f"https://{host}/{label}/-/commit/{sha}"
    return ""
