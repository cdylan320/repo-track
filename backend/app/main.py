from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from .config import settings, ROOT
from .database import Base, SessionLocal, engine
from .events import sse_stream
from .models import Account, AppMeta
from .routers import accounts, activity, settings as settings_router
from .services import git_sync, scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


def _migrate() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "accounts" not in tables:
        with engine.connect() as conn:
            for name in ("commits", "events", "pairs"):
                conn.execute(text(f"DROP TABLE IF EXISTS {name}"))
            conn.commit()
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    if "repos" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("repos")}
        with engine.connect() as conn:
            if "pushed_at" not in cols:
                conn.execute(text("ALTER TABLE repos ADD COLUMN pushed_at VARCHAR(64) DEFAULT ''"))
            if "mirrored" not in cols:
                conn.execute(text("ALTER TABLE repos ADD COLUMN mirrored BOOLEAN DEFAULT 0"))
            if "reauthored" not in cols:
                conn.execute(text("ALTER TABLE repos ADD COLUMN reauthored BOOLEAN DEFAULT 0"))
            conn.commit()
    if "accounts" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("accounts")}
        with engine.connect() as conn:
            if "poll_token_index" not in cols:
                conn.execute(text("ALTER TABLE accounts ADD COLUMN poll_token_index INTEGER"))
                conn.commit()
    from .tokens import assign_poll_token_index

    db = SessionLocal()
    try:
        pool = settings.poll_tokens_list
        if pool:
            rows = db.query(Account).order_by(Account.id.asc()).all()
            for index, account in enumerate(rows):
                if account.origin_account.lower() in settings.poll_token_map_dict:
                    continue
                if account.poll_token_index is None:
                    account.poll_token_index = assign_poll_token_index(index)
            db.commit()
    finally:
        db.close()
    with engine.connect() as conn:
        conn.execute(text("UPDATE accounts SET status = 'idle' WHERE status = 'syncing'"))
        conn.execute(
            text(
                "UPDATE accounts SET status = 'idle', last_error = '' "
                "WHERE status = 'error' AND last_error LIKE '%rate limit%'"
            )
        )
        conn.execute(
            text(
                "UPDATE repos SET reauthored = 0, status = 'idle', last_error = '' "
                "WHERE mirrored = 1 AND (last_sha IS NULL OR last_sha = '') "
                "AND pushed_at IS NOT NULL AND pushed_at != ''"
            )
        )
        conn.execute(
            text(
                "UPDATE repos SET status = 'idle', last_error = '' "
                "WHERE last_error LIKE '%cannot lock ref%' "
                "OR last_error LIKE '%reference already exists%'"
            )
        )
        conn.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    _migrate()
    db = SessionLocal()
    keep: set[int] = set()
    try:
        row = db.get(AppMeta, "poll_interval_seconds")
        if row and row.value.isdigit():
            settings.poll_interval_seconds = max(2, int(row.value))
        keep = {row.id for row in db.query(Account.id).all()}
    finally:
        db.close()
    scheduler.start()
    asyncio.create_task(asyncio.to_thread(git_sync.wipe_orphan_clones, keep))
    yield
    scheduler.stop()


app = FastAPI(title="Relay", version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accounts.router)
app.include_router(activity.router)
app.include_router(settings_router.router)
app.add_api_route("/api/events", sse_stream, methods=["GET"])


@app.get("/api/health")
def health():
    return {"ok": True, "name": "relay"}


DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    assets = DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/favicon.svg")
    def favicon():
        return FileResponse(DIST / "favicon.svg")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        target = DIST / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
