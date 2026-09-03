"""Read/write the project .env so settings changed in the UI survive a restart."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from .config import ROOT

ENV_PATH = ROOT / ".env"

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _quote(value: str) -> str:
    if value == "" or re.fullmatch(r"[A-Za-z0-9_./:@+-]*", value):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def update(values: dict[str, str]) -> None:
    """Set each key in .env, keeping existing key spelling, order and comments.

    A key already present is rewritten in place (matched case-insensitively, so the
    file's `Dest_GITHUB_TOKEN` stays as it is); anything new is appended.
    """
    wanted = {key.upper(): value for key, value in values.items()}
    if not wanted:
        return

    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        match = _LINE.match(line)
        key = match.group(1).upper() if match else ""
        if key in wanted:
            if key in seen:
                continue  # drop duplicate assignments of a key we just rewrote
            seen.add(key)
            out.append(f"{match.group(1)}={_quote(wanted[key])}")
        else:
            out.append(line)
    for key, value in wanted.items():
        if key not in seen:
            out.append(f"{key}={_quote(value)}")

    body = "\n".join(out).rstrip("\n") + "\n"
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(ENV_PATH.parent), prefix=".env.", suffix=".tmp", delete=False
    ) as tmp:
        tmp.write(body)
        temp_path = Path(tmp.name)
    os.replace(temp_path, ENV_PATH)
    ENV_PATH.chmod(0o600)
    # keep the process environment in step, so anything re-reading os.environ agrees
    for key, value in wanted.items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)
