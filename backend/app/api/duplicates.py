"""Duplicate pairs management and review endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engine.cleanup_worker import CleanupWorker
from app.models.duplicate import (
    DuplicatePair,
    DuplicatePairStatus,
    DuplicateRecord,
)

logger = logging.getLogger("arrclean.api.duplicates")

router = APIRouter(prefix="/duplicates", tags=["duplicates"])


def _serialize_record(rec: DuplicateRecord | None) -> dict[str, Any] | None:
    if not rec:
        return None
    return {
        "id": rec.id,
        "media_type": rec.media_type,
        "tmdb_id": rec.tmdb_id,
        "tvdb_id": rec.tvdb_id,
        "imdb_id": rec.imdb_id,
        "title": rec.title,
        "season": rec.season,
        "episode": rec.episode,
        "edition": rec.edition,
        "file_path": rec.file_path,
        "file_size_bytes": rec.file_size_bytes,
        "resolution": rec.resolution,
        "hdr_format": rec.hdr_format,
        "source_type": rec.source_type,
        "audio_codec": rec.audio_codec,
        "video_codec": rec.video_codec,
        "video_bitrate": rec.video_bitrate,
        "custom_format_score": rec.custom_format_score,
        "quality_profile_rank": rec.quality_profile_rank,
        "composite_quality_score": round(rec.composite_quality_score, 1),
        "is_hardlinked": rec.is_hardlinked,
        "inode_number": rec.inode_number,
        "torrent_hash": rec.torrent_hash,
    }


def _serialize_pair(pair: DuplicatePair) -> dict[str, Any]:
    return {
        "id": pair.id,
        "media_type": pair.media_type,
        "title": pair.title,
        "tmdb_id": pair.tmdb_id,
        "tvdb_id": pair.tvdb_id,
        "status": pair.status.value,
        "action_taken": pair.action_taken.value,
        "space_saved_bytes": pair.space_saved_bytes,
        "winner": _serialize_record(pair.winner),
        "loser": _serialize_record(pair.loser),
        "created_at": pair.created_at.isoformat() if pair.created_at else None,
        "resolved_at": pair.resolved_at.isoformat() if pair.resolved_at else None,
    }


@router.get("")
async def list_duplicates(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = None,
    media_type: str | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List duplicate pairs with pagination, search, and filtering."""
    stmt = select(DuplicatePair)

    if status:
        try:
            status_enum = DuplicatePairStatus(status.upper())
            stmt = stmt.where(DuplicatePair.status == status_enum)
        except ValueError:
            pass

    if media_type:
        stmt = stmt.where(DuplicatePair.media_type == media_type.lower())

    if search:
        stmt = stmt.where(DuplicatePair.title.ilike(f"%{search}%"))

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # Paginate
    stmt = stmt.order_by(DuplicatePair.id.desc()).offset((page - 1) * limit).limit(limit)
    pairs = list((await db.execute(stmt)).scalars().all())

    return {
        "items": [_serialize_pair(p) for p in pairs],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if total > 0 else 1,
    }


@router.get("/{pair_id}")
async def get_duplicate(pair_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Retrieve full details of a specific duplicate pair."""
    stmt = select(DuplicatePair).where(DuplicatePair.id == pair_id)
    pair = (await db.execute(stmt)).scalar_one_or_none()
    if not pair:
        raise HTTPException(status_code=404, detail=f"Duplicate pair {pair_id} not found")
    return _serialize_pair(pair)


@router.post("/{pair_id}/approve")
async def approve_duplicate(pair_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Approve the designated winner and execute or queue cleanup."""
    stmt = select(DuplicatePair).where(DuplicatePair.id == pair_id)
    pair = (await db.execute(stmt)).scalar_one_or_none()
    if not pair:
        raise HTTPException(status_code=404, detail=f"Duplicate pair {pair_id} not found")

    pair.status = DuplicatePairStatus.APPROVED
    await db.commit()

    # Dispatch to cleanup worker
    worker = CleanupWorker()
    result = await worker.process_pair(pair_id)
    return {"status": "approved", "result": result}


@router.post("/{pair_id}/swap")
async def swap_winner_loser(pair_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Invert the winner and loser in a duplicate pair."""
    stmt = select(DuplicatePair).where(DuplicatePair.id == pair_id)
    pair = (await db.execute(stmt)).scalar_one_or_none()
    if not pair:
        raise HTTPException(status_code=404, detail=f"Duplicate pair {pair_id} not found")

    # Swap IDs
    old_winner_id = pair.winner_record_id
    pair.winner_record_id = pair.loser_record_id
    pair.loser_record_id = old_winner_id

    # Update space_saved_bytes with new loser size
    await db.flush()
    loser_stmt = select(DuplicateRecord).where(DuplicateRecord.id == pair.loser_record_id)
    new_loser = (await db.execute(loser_stmt)).scalar_one_or_none()
    if new_loser:
        pair.space_saved_bytes = new_loser.file_size_bytes

    await db.commit()
    # Reload and serialize
    refreshed = (await db.execute(stmt)).scalar_one()
    return {"status": "swapped", "pair": _serialize_pair(refreshed)}


@router.post("/{pair_id}/ignore")
async def ignore_duplicate(pair_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Ignore this duplicate pair, preventing further automatic cleanup."""
    stmt = select(DuplicatePair).where(DuplicatePair.id == pair_id)
    pair = (await db.execute(stmt)).scalar_one_or_none()
    if not pair:
        raise HTTPException(status_code=404, detail=f"Duplicate pair {pair_id} not found")

    pair.status = DuplicatePairStatus.IGNORED
    await db.commit()
    return {"status": "ignored", "id": pair_id}


@router.post("/{pair_id}/force-delete")
async def force_delete_duplicate(pair_id: int) -> dict[str, Any]:
    """Force delete the loser file immediately, bypassing seed retention and dry-run."""
    worker = CleanupWorker()
    result = await worker.process_pair(pair_id, force_delete=True)
    return {"status": "executed", "result": result}


@router.post("/approve-all")
async def approve_all_duplicates(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Bulk approve all pending duplicate pairs and process cleanup."""
    stmt = select(DuplicatePair).where(DuplicatePair.status == DuplicatePairStatus.PENDING_REVIEW)
    pending_pairs = list((await db.execute(stmt)).scalars().all())

    for p in pending_pairs:
        p.status = DuplicatePairStatus.APPROVED
    await db.commit()

    worker = CleanupWorker()
    res = await worker.process_all_approved()
    return {
        "status": "bulk_approved",
        "count": len(pending_pairs),
        "cleanup_summary": res,
    }
