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
            conn.commit()
    with engine.connect() as conn:
        conn.execute(text("UPDATE accounts SET status = 'idle' WHERE status = 'syncing'"))
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
