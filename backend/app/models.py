from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AppMeta(Base):
    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256), default="")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin_account: Mapped[str] = mapped_column(String(160), index=True)
    origin_kind: Mapped[str] = mapped_column(String(24), default="User")
    name: Mapped[str] = mapped_column(String(160), default="")
    sync_mode: Mapped[str] = mapped_column(String(32), default="ff-only")
    include_forks: Mapped[bool] = mapped_column(Boolean, default=False)
    poll_token_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paused: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(32), default="idle")
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    repos: Mapped[list["Repo"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    commits: Mapped[list["Commit"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    events: Mapped[list["Event"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class Repo(Base):
    __tablename__ = "repos"
    __table_args__ = (UniqueConstraint("account_id", "name", name="uq_account_repo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    origin_url: Mapped[str] = mapped_column(String(512), default="")
    dest_url: Mapped[str] = mapped_column(String(512), default="")
    default_branch: Mapped[str] = mapped_column(String(120), default="main")
    private: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sha: Mapped[str] = mapped_column(String(64), default="")
    pushed_at: Mapped[str] = mapped_column(String(64), default="")
    mirrored: Mapped[bool] = mapped_column(Boolean, default=False)
    reauthored: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="idle")
    commits_synced: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    account: Mapped["Account"] = relationship(back_populates="repos")
    commits: Mapped[list["Commit"]] = relationship(back_populates="repo")


class Commit(Base):
    __tablename__ = "commits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"))
    sha: Mapped[str] = mapped_column(String(64), index=True)
    short_sha: Mapped[str] = mapped_column(String(12))
    message: Mapped[str] = mapped_column(Text, default="")
    author_name: Mapped[str] = mapped_column(String(160), default="")
    author_email: Mapped[str] = mapped_column(String(240), default="")
    authored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    files_changed: Mapped[int] = mapped_column(Integer, default=0)
    insertions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    files_list: Mapped[str] = mapped_column(Text, default="")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    account: Mapped["Account"] = relationship(back_populates="commits")
    repo: Mapped["Repo"] = relationship(back_populates="commits")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    repo_id: Mapped[int | None] = mapped_column(ForeignKey("repos.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    account: Mapped["Account | None"] = relationship(back_populates="events")
