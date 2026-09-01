from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    discord_webhook_url: str = ""
    github_token: str = ""
    git_token: str = ""
    dest_github_token: str = Field(
        default="",
        validation_alias=AliasChoices("DEST_GITHUB_TOKEN", "Dest_GITHUB_TOKEN", "dest_github_token"),
    )
    dest_github_tokens: str = Field(
        default="",
        validation_alias=AliasChoices("DEST_GITHUB_TOKENS", "dest_github_tokens"),
    )
    poll_tokens: str = Field(
        default="",
        validation_alias=AliasChoices("POLL_TOKENS", "poll_tokens"),
    )
    poll_token_map: str = Field(
        default="",
        validation_alias=AliasChoices("POLL_TOKEN_MAP", "poll_token_map"),
    )
    dest_github_account: str = Field(
        default="",
        validation_alias=AliasChoices("DEST_GITHUB_ACCOUNT", "Dest_GITHUB_ACCOUNT", "dest_github_account"),
    )
    poll_interval_seconds: int = 60
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'relay.db'}"
    clones_dir: Path = BACKEND_DIR / "data" / "clones"
    git_timeout_seconds: int = 180
    host: str = "0.0.0.0"
    port: int = 6001

    @property
    def origin_token(self) -> str:
        return (self.github_token or self.git_token).strip()

    @property
    def dest_token(self) -> str:
        tokens = self.dest_tokens_list
        return tokens[0] if tokens else ""

    @property
    def dest_tokens_list(self) -> list[str]:
        raw = self.dest_github_tokens.strip()
        if raw:
            return [t.strip() for t in raw.split(",") if t.strip()]
        token = self.dest_github_token.strip()
        return [token] if token else []

    @property
    def poll_tokens_list(self) -> list[str]:
        raw = self.poll_tokens.strip()
        if not raw:
            return []
        return [t.strip() for t in raw.split(",") if t.strip()]

    @property
    def poll_token_map_dict(self) -> dict[str, str]:
        raw = self.poll_token_map.strip()
        out: dict[str, str] = {}
        if not raw:
            return out
        for part in raw.split(","):
            piece = part.strip()
            if ":" not in piece:
                continue
            login, token = piece.split(":", 1)
            login = login.strip().lower()
            token = token.strip()
            if login and token:
                out[login] = token
        return out

    @property
    def dest_account(self) -> str:
        return self.dest_github_account.strip().strip("/")

    @property
    def poll_token(self) -> str:
        """Token for GitHub API reads (origin listing). Falls back to dest token for rate limits."""
        return self.origin_token or self.dest_token

    @property
    def poll_auth(self) -> str:
        if self.poll_tokens_list or self.poll_token_map_dict:
            return "multi"
        if self.origin_token:
            return "origin"
        if self.dest_token:
            return "dest"
        return "public"

    @property
    def api_token(self) -> str:
        return self.poll_token


settings = Settings()
settings.clones_dir.mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data").mkdir(parents=True, exist_ok=True)
