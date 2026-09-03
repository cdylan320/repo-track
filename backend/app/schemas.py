from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from .github import parse_account
from .timeutil import UtcDatetime, UtcDatetimeOpt


class AccountCreate(BaseModel):
    origin_account: str
    name: str = ""
    sync_mode: str = "ff-only"
    include_forks: bool = False

    @field_validator("origin_account")
    @classmethod
    def validate_account(cls, value: str) -> str:
        login = parse_account(value)
        if not login:
            raise ValueError("GitHub account is required")
        return login

    @field_validator("sync_mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        if value not in {"ff-only", "force"}:
            raise ValueError("sync_mode must be ff-only or force")
        return value


class AccountUpdate(BaseModel):
    name: str | None = None
    origin_account: str | None = None
    sync_mode: str | None = None
    include_forks: bool | None = None
    paused: bool | None = None

    @field_validator("origin_account")
    @classmethod
    def validate_account(cls, value: str | None) -> str | None:
        if value is None:
            return value
        login = parse_account(value)
        if not login:
            raise ValueError("GitHub account is required")
        return login


class RepoOut(BaseModel):
    id: int
    account_id: int
    name: str
    origin_url: str
    dest_url: str
    default_branch: str
    private: bool
    last_sha: str
    pushed_at: str = ""
    mirrored: bool = False
    last_sync_at: UtcDatetimeOpt
    last_error: str
    status: str
    commits_synced: int

    class Config:
        from_attributes = True


class AccountOut(BaseModel):
    id: int
    origin_account: str
    origin_kind: str
    dest_account: str
    name: str
    sync_mode: str
    include_forks: bool
    paused: bool
    status: str
    last_error: str
    last_sync_at: UtcDatetimeOpt
    created_at: UtcDatetime
    updated_at: UtcDatetime
    repo_count: int = 0
    commits_synced: int = 0
    commits_today: int = 0
    poll_token_hint: str = ""
    poll_auth: str = "public"
    github_remaining: int | None = None
    github_paused_until: UtcDatetimeOpt = None
    repos: list[RepoOut] = []

    class Config:
        from_attributes = True


class CommitOut(BaseModel):
    kind: str = "commit"
    id: int
    account_id: int
    repo_id: int
    sha: str
    short_sha: str
    message: str
    author_name: str
    author_email: str
    authored_at: UtcDatetimeOpt
    files_changed: int
    insertions: int
    deletions: int
    files_list: str = ""
    synced_at: UtcDatetime
    origin_label: str = ""
    dest_label: str = ""
    origin_url: str = ""
    dest_url: str = ""
    repo_name: str = ""
    account_name: str = ""

    class Config:
        from_attributes = True


class EventOut(BaseModel):
    id: int
    account_id: int | None
    repo_id: int | None
    kind: str
    message: str
    detail: str
    created_at: UtcDatetime
    origin_label: str = ""
    dest_label: str = ""

    class Config:
        from_attributes = True


class GithubBucketOut(BaseModel):
    key: str
    hint: str
    remaining: int
    paused_until: UtcDatetimeOpt = None
    accounts: list[str] = []


class OverviewOut(BaseModel):
    account_count: int
    pair_count: int = 0
    active_count: int
    paused_count: int
    error_count: int
    repo_count: int
    commits_today: int
    commits_total: int
    last_sync_at: UtcDatetimeOpt
    poll_interval_seconds: int
    discord_configured: bool
    dest_account: str
    dest_token_configured: bool
    origin_token_configured: bool
    git_token_configured: bool
    worker_running: bool
    next_tick_at: UtcDatetimeOpt = None
    github_paused_until: UtcDatetimeOpt = None
    github_remaining: int | None = None
    poll_auth: str = "public"
    github_buckets: list[GithubBucketOut] = []
    recommended_poll_seconds: int = 10
    rate_limited_count: int = 0


class SettingsOut(BaseModel):
    poll_interval_seconds: int
    discord_configured: bool
    discord_webhook_hint: str
    dest_account: str
    dest_token_configured: bool
    dest_token_hint: str
    origin_token_configured: bool
    origin_token_hint: str
    git_token_configured: bool
    git_token_hint: str
    poll_auth: str = "public"
    github_remaining: int | None = None
    github_paused_until: str | None = None
    poll_tokens_configured: int = 0
    poll_token_map_configured: int = 0
    dest_tokens_configured: int = 0
    dest_token_hints: list[str] = []
    recommended_poll_seconds: int = 10
    github_buckets: list[GithubBucketOut] = []


class SettingsUpdate(BaseModel):
    poll_interval_seconds: int | None = Field(default=None, ge=2, le=3600)
    dest_account: str | None = None
    dest_token: str | None = None

    @field_validator("dest_account")
    @classmethod
    def validate_dest_account(cls, value: str | None) -> str | None:
        if value is None:
            return value
        login = parse_account(value)
        if not login:
            raise ValueError("Destination GitHub account is required")
        return login

    @field_validator("dest_token")
    @classmethod
    def validate_dest_token(cls, value: str | None) -> str | None:
        if value is None:
            return value
        tokens = [t.strip() for t in value.split(",") if t.strip()]
        if not tokens:
            raise ValueError("Destination token is required")
        return ",".join(tokens)


class DiscordTestResult(BaseModel):
    ok: bool
    message: str
