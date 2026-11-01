"""Background seed monitor tracking and purging torrents once retention criteria are met."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.models.duplicate import (
    ActionTaken,
    DuplicatePair,
    DuplicatePairStatus,
)
from app.models.seed_lock import SeedLockEntry, SeedLockStatus
from app.services import ServiceManager, get_service_manager

logger = logging.getLogger("arrclean.engine.seed_monitor")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def reconcile_seed_lock_entries(
    session: AsyncSession,
    service_manager: ServiceManager | None = None,
    settings: Settings | None = None,
) -> dict[str, int]:
    """Reconcile DuplicatePair records in SEED_LOCKED status with SeedLockEntry rows.

    - If a pair is SEED_LOCKED but has no SeedLockEntry:
        - If file is gone and not in qBittorrent: marks pair COMPLETED.
        - If Safe Mode is enabled (DRY_RUN=True): resets pair to APPROVED so it can run live.
        - If live mode and file/torrent exists: backfills the missing SeedLockEntry.
    - If a SeedLockEntry exists for a pair that is COMPLETED: marks SeedLockEntry as PURGED.
    """
    services = service_manager or get_service_manager()
    settings = settings or get_settings()

    stats = {
        "backfilled": 0,
        "completed": 0,
        "reset_to_approved": 0,
    }

    stmt = (
        select(DuplicatePair)
        .where(DuplicatePair.status == DuplicatePairStatus.SEED_LOCKED)
    )
    seed_pairs = list((await session.execute(stmt)).scalars().all())

    for pair in seed_pairs:
        entry_stmt = select(SeedLockEntry).where(SeedLockEntry.duplicate_pair_id == pair.id)
        existing = (await session.execute(entry_stmt)).scalar_one_or_none()
        if existing:
            continue

        loser = pair.loser
        if not loser:
            continue

        loser_path = loser.file_path or ""
        torrent_hash = loser.torrent_hash

        seed_info = {}
        if services.qbittorrent.is_configured:
            if not torrent_hash and loser_path:
                try:
                    t = await services.qbittorrent.find_torrent_by_file_path(loser_path, deep_search=True)
                    if t:
                        torrent_hash = t.get("hash")
                        loser.torrent_hash = torrent_hash
                except Exception as ex:
                    logger.debug("Failed torrent lookup for loser %s: %s", loser_path, ex)

            if torrent_hash:
                try:
                    seed_info = await services.qbittorrent.get_torrent_seeding_info(
                        torrent_hash=torrent_hash,
                        min_ratio=settings.MIN_SEED_RATIO,
                        min_days=settings.MIN_SEED_DAYS,
                    )
                except Exception as ex:
                    logger.debug("Failed seeding info fetch for hash %s: %s", torrent_hash, ex)

        file_exists = os.path.exists(loser_path) if loser_path else False
        in_qb = bool(torrent_hash and seed_info)

        if not file_exists and not in_qb:
            # File is already deleted and not seeding; complete pair
            pair.status = DuplicatePairStatus.COMPLETED
            pair.action_taken = ActionTaken.DELETED
            pair.resolved_at = _utcnow()
            stats["completed"] += 1
            continue

        if settings.DRY_RUN:
            # Safe mode: unlinked simulation pair should be approved for live execution
            pair.status = DuplicatePairStatus.APPROVED
            stats["reset_to_approved"] += 1
            continue

        # Live mode: backfill SeedLockEntry
        torrent_name = (
            seed_info.get("name")
            or (os.path.basename(loser_path) if loser_path else pair.title)
        )
        current_ratio = seed_info.get("ratio", 0.0)
        current_seed_days = int(seed_info.get("seeding_time_days", 0))

        remaining_days = max(0, settings.MIN_SEED_DAYS - current_seed_days)
        estimated_unlock = _utcnow() + timedelta(days=remaining_days)

        seed_entry = SeedLockEntry(
            duplicate_pair_id=pair.id,
            torrent_hash=torrent_hash or "unknown",
            torrent_name=torrent_name,
            file_path=loser_path,
            current_ratio=current_ratio,
            target_ratio=settings.MIN_SEED_RATIO,
            current_seed_days=current_seed_days,
            target_seed_days=settings.MIN_SEED_DAYS,
            status=SeedLockStatus.SEEDING,
            estimated_unlock_date=estimated_unlock,
            created_at=pair.created_at or _utcnow(),
        )
        session.add(seed_entry)
        stats["backfilled"] += 1

    return stats


class SeedMonitor:
    """Monitors the Pending Seed Completion queue and purges torrents when rules are satisfied."""

    def __init__(
        self,
        service_manager: ServiceManager | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.services = service_manager or get_service_manager()
        self.session_factory = session_factory
        self.settings = settings or get_settings()

    async def check_seed_locks(self) -> dict[str, Any]:
        """Poll qBittorrent for all active seed-locked items and purge those that met requirements."""
        if not self.services.qbittorrent.is_configured:
            logger.debug("qBittorrent is not configured; skipping seed monitor check.")
            return {"checked": 0, "purged": 0, "space_reclaimed_bytes": 0}

        if self.session_factory is None:
            from app.database import get_session_factory
            self.session_factory = get_session_factory()

        checked_count = 0
        purged_count = 0
        space_reclaimed = 0

        async with self.session_factory() as session:
            # Reconcile any orphaned SEED_LOCKED pairs before checking progress
            await reconcile_seed_lock_entries(session, self.services, self.settings)

            stmt = select(SeedLockEntry).where(SeedLockEntry.status == SeedLockStatus.SEEDING)
            res = await session.execute(stmt)
            active_entries = list(res.scalars().all())

            for entry in active_entries:
                checked_count += 1
                try:
                    info = await self.services.qbittorrent.get_torrent_seeding_info(
                        torrent_hash=entry.torrent_hash,
                        min_ratio=entry.target_ratio,
                        min_days=entry.target_seed_days,
                    )

                    entry.current_ratio = info.get("ratio", 0.0)
                    entry.current_seed_days = int(info.get("seeding_time_days", 0))
                    entry.updated_at = _utcnow()

                    # Calculate estimated unlock date based on days remaining
                    remaining_days = max(0, entry.target_seed_days - entry.current_seed_days)
                    entry.estimated_unlock_date = _utcnow() + timedelta(days=remaining_days)

                    if info.get("can_delete"):
                        # Threshold reached! Purge from qBittorrent and disk
                        logger.info(
                            "Seed retention requirement met for torrent %s (Ratio: %.2f/%.2f, Days: %d/%d). Purging...",
                            entry.torrent_name,
                            entry.current_ratio,
                            entry.target_ratio,
                            entry.current_seed_days,
                            entry.target_seed_days,
                        )

                        await self.services.qbittorrent.delete_torrent(
                            entry.torrent_hash, delete_files=True
                        )

                        # Delete leftover file on disk if it still exists
                        from app.engine.hardlink_utils import HardlinkUtils
                        if os.path.exists(entry.file_path) and HardlinkUtils.is_safe_file_path(entry.file_path):
                            try:
                                os.remove(entry.file_path)
                                logger.info("Deleted remaining seed file from disk: %s", entry.file_path)
                            except Exception as rm_err:
                                logger.debug("Could not remove seed file %s: %s", entry.file_path, rm_err)

                        entry.status = SeedLockStatus.PURGED
                        entry.purged_at = _utcnow()

                        # Update associated duplicate pair
                        pair_stmt = select(DuplicatePair).where(DuplicatePair.id == entry.duplicate_pair_id)
                        p_res = await session.execute(pair_stmt)
                        pair = p_res.scalar_one_or_none()
                        if pair:
                            pair.status = DuplicatePairStatus.COMPLETED
                            pair.action_taken = ActionTaken.DELETED
                            pair.resolved_at = _utcnow()
                            if pair.loser:
                                space_reclaimed += pair.loser.file_size_bytes
                            if pair.winner and pair.loser:
                                try:
                                    from app.engine.cleanup_worker import CleanupWorker
                                    worker = CleanupWorker(
                                        service_manager=self.services,
                                        settings=self.settings,
                                    )
                                    await worker._post_cleanup_reconcile(pair.winner, pair.loser)
                                except Exception as recon_err:
                                    logger.debug("Post-cleanup reconcile error in seed monitor: %s", recon_err)

                        purged_count += 1

                except Exception as e:
                    logger.warning("Error checking seed lock for torrent %s: %s", entry.torrent_hash, e)

            await session.commit()

        logger.info(
            "Seed monitor run complete: checked %d, purged %d (%d bytes reclaimed)",
            checked_count,
            purged_count,
            space_reclaimed,
        )

        return {
            "checked": checked_count,
            "purged": purged_count,
            "space_reclaimed_bytes": space_reclaimed,
        }
