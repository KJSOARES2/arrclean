"""FastAPI application entry point for ArrClean."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.api.websocket import BroadcastLogHandler
from app.config import get_settings
from app.database import close_db, init_db
from app.scheduler.jobs import start_scheduler, stop_scheduler
from app.services import get_service_manager

# Configure logging
settings = get_settings()
log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Silence routine per-request HTTP access logging from httpx/httpcore
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

root_logger = logging.getLogger()
root_logger.addHandler(BroadcastLogHandler())
logger = logging.getLogger("arrclean.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle management."""
    logger.info("Initializing ArrClean backend...")

    # Ensure data directory exists
    os.makedirs("./data", exist_ok=True)

    # Initialize DB tables
    await init_db()

    # Reset any stale RUNNING scan jobs interrupted by a server restart
    try:
        from app.database import get_session_factory
        from app.models.job_history import JobStatus, ScanJob
        from datetime import datetime, timezone
        from sqlalchemy import select
        async with get_session_factory()() as session:
            stale_stmt = select(ScanJob).where(ScanJob.status == JobStatus.RUNNING)
            stale_jobs = list((await session.execute(stale_stmt)).scalars().all())
            for sj in stale_jobs:
                sj.status = JobStatus.FAILED
                sj.error_message = "Scan interrupted by system restart."
                sj.completed_at = datetime.now(timezone.utc)
            if stale_jobs:
                await session.commit()
                logger.info("Marked %d interrupted scan jobs as failed", len(stale_jobs))
    except Exception as e:
        logger.debug("Stale job cleanup skipped: %s", e)

    # Load persistent settings overrides from DB
    try:
        from app.database import get_session_factory
        from app.models.settings import AppSettings
        from sqlalchemy import select
        import json
        async with get_session_factory()() as session:
            stmt = select(AppSettings)
            db_overrides = list((await session.execute(stmt)).scalars().all())
            if db_overrides:
                override_dict = {}
                for o in db_overrides:
                    try:
                        override_dict[o.key] = json.loads(o.value)
                    except Exception:
                        pass
                from app.config import reload_settings
                effective_settings = reload_settings(override_dict)
                get_service_manager().reload(effective_settings)
                logger.info("Loaded %d settings overrides from database", len(override_dict))
    except Exception as e:
        logger.warning("Could not pre-load DB settings overrides: %s", e)

    # Start background scheduler
    start_scheduler()

    yield

    logger.info("Shutting down ArrClean backend...")
    stop_scheduler()
    await get_service_manager().close_all()
    await close_db()


app = FastAPI(
    title="ArrClean",
    description="Automated Media Deduplication & Lifecycle Manager",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health checks
@app.get("/health", tags=["health"])
@app.get("/api/v1/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "ArrClean", "version": "1.0.0"}


# WebSocket alias for root /ws/logs
@app.websocket("/ws/logs")
async def websocket_logs_root_alias(websocket: WebSocket) -> None:
    from app.api.websocket import websocket_logs_endpoint
    await websocket_logs_endpoint(websocket)


# Mount API router
app.include_router(api_router)

# Mount frontend build if available
frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if not frontend_dist.exists():
    frontend_dist = Path("/app/frontend/dist")

if frontend_dist.exists() and (frontend_dist / "index.html").exists():
    logger.info("Mounting frontend SPA from %s", frontend_dist)
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> Response:
        file_path = frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_dist / "index.html")
else:
    logger.info("Frontend dist directory not found at %s. Running in API-only mode.", frontend_dist)
