"""Dashboard analytics and telemetry endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.duplicate import DuplicatePair, DuplicatePairStatus, DuplicateRecord
from app.models.job_history import JobStatus, ScanJob
from app.models.seed_lock import SeedLockEntry, SeedLockStatus

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Retrieve aggregate storage statistics, pair counts, and active scan status."""
    # 1. Total Space Reclaimed (COMPLETED pairs)
    reclaimed_stmt = select(func.coalesce(func.sum(DuplicatePair.space_saved_bytes), 0)).where(
        DuplicatePair.status == DuplicatePairStatus.COMPLETED
    )
    total_reclaimed = (await db.execute(reclaimed_stmt)).scalar() or 0

    # 2. Pending Space (SEED_LOCKED or PENDING_REVIEW)
    pending_stmt = select(func.coalesce(func.sum(DuplicatePair.space_saved_bytes), 0)).where(
        DuplicatePair.status.in_([DuplicatePairStatus.SEED_LOCKED, DuplicatePairStatus.PENDING_REVIEW])
    )
    pending_reclaim = (await db.execute(pending_stmt)).scalar() or 0

    # 3. Counts
    total_found_stmt = select(func.count(DuplicatePair.id))
    total_found = (await db.execute(total_found_stmt)).scalar() or 0

    resolved_stmt = select(func.count(DuplicatePair.id)).where(
        DuplicatePair.status == DuplicatePairStatus.COMPLETED
    )
    resolved_count = (await db.execute(resolved_stmt)).scalar() or 0

    pending_review_stmt = select(func.count(DuplicatePair.id)).where(
        DuplicatePair.status == DuplicatePairStatus.PENDING_REVIEW
    )
    pending_review_count = (await db.execute(pending_review_stmt)).scalar() or 0

    seed_locked_stmt = select(func.count(DuplicatePair.id)).where(
        DuplicatePair.status == DuplicatePairStatus.SEED_LOCKED
    )
    seed_locked_count = (await db.execute(seed_locked_stmt)).scalar() or 0

    # 4. Active Scan Job
    active_job_stmt = (
        select(ScanJob)
        .where(ScanJob.status == JobStatus.RUNNING)
        .order_by(ScanJob.started_at.desc())
        .limit(1)
    )
    active_job = (await db.execute(active_job_stmt)).scalar_one_or_none()

    # 5. Last Completed Job
    last_job_stmt = (
        select(ScanJob)
        .where(ScanJob.status == JobStatus.COMPLETED)
        .order_by(ScanJob.completed_at.desc())
        .limit(1)
    )
    last_job = (await db.execute(last_job_stmt)).scalar_one_or_none()

    return {
        "total_space_reclaimed_bytes": total_reclaimed,
        "pending_space_to_reclaim_bytes": pending_reclaim,
        "duplicates_found_count": total_found,
        "duplicates_resolved_count": resolved_count,
        "pending_review_count": pending_review_count,
        "seed_locked_count": seed_locked_count,
        "active_scan": {
            "id": active_job.id,
            "type": active_job.job_type.value,
            "started_at": active_job.started_at.isoformat(),
        }
        if active_job
        else None,
        "last_scan_completed_at": last_job.completed_at.isoformat() if last_job and last_job.completed_at else None,
    }


@router.get("/history")
async def get_dashboard_history(
    days: int = 30, db: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    """Retrieve daily reclaimed storage history for chart plotting."""
    start_date = _utcnow() - timedelta(days=days)

    stmt = (
        select(
            func.date(DuplicatePair.resolved_at).label("day"),
            func.coalesce(func.sum(DuplicatePair.space_saved_bytes), 0).label("space_saved"),
            func.count(DuplicatePair.id).label("count"),
        )
        .where(
            DuplicatePair.status == DuplicatePairStatus.COMPLETED,
            DuplicatePair.resolved_at >= start_date,
        )
        .group_by("day")
        .order_by("day")
    )
    rows = (await db.execute(stmt)).all()
    history_map = {str(r.day): (r.space_saved, r.count) for r in rows if r.day}

    # Generate full sequence of days
    result: list[dict[str, Any]] = []
    current = start_date
    now = _utcnow()
    cumulative = 0

    while current <= now:
        day_str = current.strftime("%Y-%m-%d")
        daily_saved, count = history_map.get(day_str, (0, 0))
        cumulative += daily_saved
        result.append({
            "date": day_str,
            "space_reclaimed_bytes": daily_saved,
            "space_reclaimed_gb": round(daily_saved / (1024**3), 2),
            "cumulative_gb": round(cumulative / (1024**3), 2),
            "duplicates_resolved": count,
        })
        current += timedelta(days=1)

    return result


@router.get("/breakdown")
async def get_dashboard_breakdown(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Retrieve categorization breakdowns by resolution, HDR format, and source type."""
    # 1. Resolution breakdown
    res_stmt = (
        select(
            DuplicateRecord.resolution,
            func.count(DuplicateRecord.id),
        )
        .group_by(DuplicateRecord.resolution)
    )
    res_rows = (await db.execute(res_stmt)).all()
    resolution_counts = {r[0] or "Unknown": r[1] for r in res_rows}

    # 2. HDR breakdown
    hdr_stmt = (
        select(
            DuplicateRecord.hdr_format,
            func.count(DuplicateRecord.id),
        )
        .group_by(DuplicateRecord.hdr_format)
    )
    hdr_rows = (await db.execute(hdr_stmt)).all()
    hdr_counts = {h[0] or "SDR": h[1] for h in hdr_rows}

    # 3. Source (Torrent vs Usenet)
    torrent_stmt = select(func.count(DuplicateRecord.id)).where(DuplicateRecord.torrent_hash.isnot(None))
    torrent_count = (await db.execute(torrent_stmt)).scalar() or 0

    total_records_stmt = select(func.count(DuplicateRecord.id))
    total_records = (await db.execute(total_records_stmt)).scalar() or 0
    usenet_count = max(0, total_records - torrent_count)

    return {
        "by_resolution": [
            {"name": k, "value": v} for k, v in resolution_counts.items()
        ],
        "by_hdr": [
            {"name": k, "value": v} for k, v in hdr_counts.items()
        ],
        "by_source": [
            {"name": "Torrent", "value": torrent_count},
            {"name": "Usenet / Direct", "value": usenet_count},
        ],
    }


@router.get("/recent-activity")
async def get_recent_activity(
    limit: int = 10, db: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    """Retrieve recent cleanup activity entries."""
    stmt = (
        select(DuplicatePair)
        .order_by(DuplicatePair.created_at.desc())
        .limit(limit)
    )
    pairs = list((await db.execute(stmt)).scalars().all())

    return [
        {
            "id": p.id,
            "title": p.title,
            "media_type": p.media_type,
            "status": p.status.value,
            "action_taken": p.action_taken.value,
            "space_saved_bytes": p.space_saved_bytes,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "resolved_at": p.resolved_at.isoformat() if p.resolved_at else None,
        }
        for p in pairs
    ]
