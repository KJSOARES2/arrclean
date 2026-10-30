"""Endpoints for managing the qBittorrent seed-lock watchlist."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engine.seed_monitor import SeedMonitor
from app.models.duplicate import ActionTaken, DuplicatePair, DuplicatePairStatus
from app.models.seed_lock import SeedLockEntry, SeedLockStatus
from app.services import get_service_manager

logger = logging.getLogger("arrclean.api.seed_watch")

router = APIRouter(prefix="/seed-watch", tags=["seed-watch"])


@router.get("")
async def list_seed_watch(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    """List all entries in the Seed-Lock queue with live progress metrics."""
    stmt = (
        select(SeedLockEntry)
        .order_by(SeedLockEntry.status.asc(), SeedLockEntry.created_at.desc())
    )
    entries = list((await db.execute(stmt)).scalars().all())

    items: list[dict[str, Any]] = []
    for e in entries:
        pair_title = e.duplicate_pair.title if e.duplicate_pair else "Unknown"
        media_type = e.duplicate_pair.media_type if e.duplicate_pair else "movie"
        items.append({
            "id": e.id,
            "duplicate_pair_id": e.duplicate_pair_id,
            "title": pair_title,
            "media_type": media_type,
            "torrent_name": e.torrent_name,
            "torrent_hash": e.torrent_hash,
            "file_path": e.file_path,
            "current_ratio": round(e.current_ratio, 2),
            "target_ratio": round(e.target_ratio, 2),
            "ratio_progress_percent": min(100.0, round((e.current_ratio / e.target_ratio * 100), 1)) if e.target_ratio > 0 else 0,
            "current_seed_days": e.current_seed_days,
            "target_seed_days": e.target_seed_days,
            "days_progress_percent": min(100.0, round((e.current_seed_days / e.target_seed_days * 100), 1)) if e.target_seed_days > 0 else 0,
            "status": e.status.value,
            "estimated_unlock_date": e.estimated_unlock_date.isoformat() if e.estimated_unlock_date else None,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "purged_at": e.purged_at.isoformat() if e.purged_at else None,
        })

    return items


@router.delete("/{entry_id}")
async def force_purge_seed_entry(
    entry_id: int, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Force purge a seed-locked torrent from qBittorrent and disk immediately."""
    stmt = select(SeedLockEntry).where(SeedLockEntry.id == entry_id)
    entry = (await db.execute(stmt)).scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail=f"Seed lock entry {entry_id} not found")

    services = get_service_manager()
    if services.qbittorrent.is_configured:
        try:
            await services.qbittorrent.delete_torrent(entry.torrent_hash, delete_files=True)
        except Exception as e:
            logger.warning("Failed to delete torrent %s from qBittorrent: %s", entry.torrent_hash, e)

    entry.status = SeedLockStatus.PURGED
    entry.purged_at = _utcnow()

    # Mark pair as completed
    pair_stmt = select(DuplicatePair).where(DuplicatePair.id == entry.duplicate_pair_id)
    pair = (await db.execute(pair_stmt)).scalar_one_or_none()
    if pair:
        pair.status = DuplicatePairStatus.COMPLETED
        pair.action_taken = ActionTaken.DELETED
        pair.resolved_at = _utcnow()

    await db.commit()
    return {"status": "purged", "id": entry_id}


@router.post("/check")
async def trigger_seed_check() -> dict[str, Any]:
    """Manually trigger a seed retention check immediately."""
    monitor = SeedMonitor()
    res = await monitor.check_seed_locks()
    return {"status": "completed", "summary": res}


def _utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
