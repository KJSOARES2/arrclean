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
