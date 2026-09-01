from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer

DatetimeT = datetime | None


def utc_iso(dt: DatetimeT) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


UtcDatetime = Annotated[datetime, PlainSerializer(utc_iso, return_type=str, when_used="json")]
UtcDatetimeOpt = Annotated[datetime | None, PlainSerializer(utc_iso, return_type=str | None, when_used="json")]


def parse_github_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if "+" in raw[10:] or raw.count("-") > 2:
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
