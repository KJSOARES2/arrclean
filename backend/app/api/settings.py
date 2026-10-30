"""Settings management and scan triggering endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.engine.dedup_scanner import DedupScanner
from app.models.duplicate import DuplicatePair, DuplicateRecord
from app.models.job_history import JobStatus, ScanJob
from app.models.seed_lock import SeedLockEntry
from app.models.settings import AppSettings
from app.services import get_service_manager

logger = logging.getLogger("arrclean.api.settings")

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsUpdatePayload(BaseModel):
    DRY_RUN: bool | None = None
    SCAN_CRON: str | None = None
    SEED_MONITOR_INTERVAL_MINUTES: int | None = None
    QUEUE_CHECK_INTERVAL_MINUTES: int | None = None

    PLEX_URL: str | None = None
    PLEX_TOKEN: str | None = None

    RADARR_URL: str | None = None
    RADARR_APIKEY: str | None = None

    SONARR_URL: str | None = None
    SONARR_APIKEY: str | None = None

    QBITTORRENT_URL: str | None = None
    QBITTORRENT_USERNAME: str | None = None
    QBITTORRENT_PASSWORD: str | None = None

    SABNZBD_URL: str | None = None
    SABNZBD_APIKEY: str | None = None

    OVERSEERR_URL: str | None = None
    OVERSEERR_APIKEY: str | None = None

    PROWLARR_URL: str | None = None
    PROWLARR_APIKEY: str | None = None

    DISCORD_WEBHOOK_URL: str | None = None
    NOTIFIARR_APIKEY: str | None = None
    GOTIFY_URL: str | None = None
    GOTIFY_TOKEN: str | None = None

    MIN_SEED_RATIO: float | None = None
    MIN_SEED_DAYS: int | None = None
    EDITION_CONSOLIDATE: bool | None = None

    WEIGHT_RESOLUTION: float | None = None
    WEIGHT_HDR: float | None = None
    WEIGHT_SOURCE: float | None = None
    WEIGHT_AUDIO: float | None = None
    WEIGHT_CODEC: float | None = None


@router.get("")
async def get_all_settings(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Retrieve all current application settings, merging env defaults with DB overrides."""
    base_settings = get_settings().model_dump()

    # Query DB overrides
    stmt = select(AppSettings)
    overrides = list((await db.execute(stmt)).scalars().all())
    for item in overrides:
        try:
            val = json.loads(item.value)
            if item.key in base_settings:
                base_settings[item.key] = val
        except Exception:
            continue

    # Mask sensitive tokens for safe client display
    masked = dict(base_settings)
    for sensitive_key in [
        "PLEX_TOKEN",
        "RADARR_APIKEY",
        "SONARR_APIKEY",
        "QBITTORRENT_PASSWORD",
        "SABNZBD_APIKEY",
        "OVERSEERR_APIKEY",
        "PROWLARR_APIKEY",
        "NOTIFIARR_APIKEY",
        "GOTIFY_TOKEN",
    ]:
        if masked.get(sensitive_key):
            masked[f"{sensitive_key}_SET"] = True
            masked[sensitive_key] = "••••••••"
        else:
            masked[f"{sensitive_key}_SET"] = False

    return masked


@router.put("")
async def update_settings(
    payload: SettingsUpdatePayload, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Persist settings overrides into the database and reload runtime clients."""
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)

    for key, value in updates.items():
        # Do not overwrite with placeholder mask
        if isinstance(value, str) and ("•" in value or value == "••••••••"):
            continue

        stmt = select(AppSettings).where(AppSettings.key == key)
        record = (await db.execute(stmt)).scalar_one_or_none()
        if record:
            record.value = json.dumps(value)
        else:
            record = AppSettings(key=key, value=json.dumps(value))
            db.add(record)

    await db.commit()

    # Load all overrides from DB to build complete effective settings
    stmt_all = select(AppSettings)
    all_overrides = list((await db.execute(stmt_all)).scalars().all())
    override_dict: dict[str, Any] = {}
    for item in all_overrides:
        try:
            override_dict[item.key] = json.loads(item.value)
        except Exception:
            pass

    from app.config import reload_settings
    effective_settings = reload_settings(override_dict)

    # Reload runtime services with updated settings
    sm = get_service_manager()
    sm.reload(effective_settings)

    return {"status": "updated", "updated_keys": list(updates.keys())}


@router.post("/scan/trigger")
async def trigger_scan(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Trigger an immediate full duplicate scan in the background."""
    scanner = DedupScanner()
    background_tasks.add_task(scanner.run_full_scan)
    return {"status": "scan_started", "message": "Full deduplication scan initiated."}


@router.get("/scan/status")
async def get_scan_status(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Check the status of the current or most recent scan job."""
    stmt = (
        select(ScanJob)
        .order_by(ScanJob.started_at.desc())
        .limit(1)
    )
    job = (await db.execute(stmt)).scalar_one_or_none()

    if not job:
        return {"status": "idle", "job": None}

    return {
        "status": "running" if job.status == JobStatus.RUNNING else "idle",
        "job": {
            "id": job.id,
            "job_type": job.job_type.value,
            "status": job.status.value,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "duplicates_found": job.duplicates_found,
            "duplicates_resolved": job.duplicates_resolved,
            "space_reclaimed_bytes": job.space_reclaimed_bytes,
            "error_message": job.error_message,
        },
    }


@router.post("/reset-stats")
async def reset_statistics(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Reset duplicate records, pairs, and scan job history."""
    await db.execute(delete(SeedLockEntry))
    await db.execute(delete(DuplicatePair))
    await db.execute(delete(DuplicateRecord))
    await db.execute(delete(ScanJob))
    await db.commit()
    return {"status": "reset", "message": "All duplicate telemetry and scan jobs cleared."}
