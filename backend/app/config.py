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
        return self.dest_github_token.strip()

    @property
    def dest_account(self) -> str:
        return self.dest_github_account.strip().strip("/")

    @property
    def api_token(self) -> str:
        return self.origin_token


settings = Settings()
settings.clones_dir.mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data").mkdir(parents=True, exist_ok=True)
