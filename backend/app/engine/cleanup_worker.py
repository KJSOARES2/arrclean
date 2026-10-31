"""Cleanup worker handling safe duplicate deletion and seeding safeguards."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.engine.hardlink_utils import HardlinkUtils
from app.models.duplicate import (
    ActionTaken,
    DuplicatePair,
    DuplicatePairStatus,
    DuplicateRecord,
)
from app.models.seed_lock import SeedLockEntry, SeedLockStatus
from app.services import ServiceManager, get_service_manager

logger = logging.getLogger("arrclean.engine.cleanup_worker")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CleanupWorker:
    """Safely executes deletions for approved duplicate pairs while honoring seeding rules."""

    def __init__(
        self,
        service_manager: ServiceManager | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.services = service_manager or get_service_manager()
        self.session_factory = session_factory
        self.settings = settings or get_settings()

    async def process_pair(self, pair_id: int, force_delete: bool = False) -> dict[str, Any]:
        """Process a single duplicate pair for cleanup."""
        if self.session_factory is None:
            from app.database import get_session_factory
            self.session_factory = get_session_factory()

        async with self.session_factory() as session:
            stmt = (
                select(DuplicatePair)
                .where(DuplicatePair.id == pair_id)
            )
            res = await session.execute(stmt)
            pair = res.scalar_one_or_none()

            if not pair:
                return {"success": False, "error": f"Pair {pair_id} not found"}

            winner = pair.winner
            loser = pair.loser

            if not loser or not winner:
                return {"success": False, "error": "Winner or loser record missing"}

            # Safety verification: ensure winner and loser are compatible duplicate candidates
            from app.engine.tv_parser import TVParser
            w_cand = {"media_type": winner.media_type, "season": winner.season, "episode": winner.episode, "file_path": winner.file_path}
            l_cand = {"media_type": loser.media_type, "season": loser.season, "episode": loser.episode, "file_path": loser.file_path}
            if not TVParser.are_candidates_compatible(w_cand, l_cand):
                err = (
                    f"Safety block: Winner ({winner.file_path}) and Loser ({loser.file_path}) "
                    "belong to different seasons or episodes. Deletion aborted."
                )
                logger.error(err)
                pair.status = DuplicatePairStatus.IGNORED
                await session.commit()
                return {"success": False, "error": err}

            dry_run = self.settings.DRY_RUN and not force_delete
            logger.info(
                "Processing pair %d: %s (DryRun=%s, Force=%s)",
                pair.id,
                pair.title,
                dry_run,
                force_delete,
            )

            result = await self._execute_cleanup(
                session=session,
                pair=pair,
                winner=winner,
                loser=loser,
                dry_run=dry_run,
                force_delete=force_delete,
            )
            await session.commit()
            return result

    async def process_all_approved(self) -> dict[str, Any]:
        """Process all duplicate pairs currently in APPROVED status or pending dry-run execution."""
        if self.session_factory is None:
            from app.database import get_session_factory
            self.session_factory = get_session_factory()

        processed = 0
        space_saved = 0
        errors: list[str] = []

        # Re-fetch latest settings in case DRY_RUN changed
        self.settings = get_settings()

        target_ids: list[int] = []
        async with self.session_factory() as session:
            stmt = select(DuplicatePair).where(
                DuplicatePair.status.in_([
                    DuplicatePairStatus.APPROVED,
                    DuplicatePairStatus.SEED_LOCKED,
                ])
            )
            res = await session.execute(stmt)
            pairs_to_check = list(res.scalars().all())

            for p in pairs_to_check:
                if p.status == DuplicatePairStatus.APPROVED:
                    target_ids.append(p.id)
                elif p.status == DuplicatePairStatus.SEED_LOCKED:
                    # Check if an actual SeedLockEntry row exists in database
                    entry_stmt = select(SeedLockEntry).where(SeedLockEntry.duplicate_pair_id == p.id)
                    entry = (await session.execute(entry_stmt)).scalar_one_or_none()
                    if not entry:
                        # Orphaned dry-run simulation pair; reset to APPROVED so it executes
                        p.status = DuplicatePairStatus.APPROVED
                        target_ids.append(p.id)
            await session.commit()

        for pid in target_ids:
            res = await self.process_pair(pid)
            if res.get("success"):
                processed += 1
                space_saved += res.get("space_saved", 0)
            else:
                errors.append(f"Pair {pid}: {res.get('error')}")

        return {
            "processed": processed,
            "space_saved_bytes": space_saved,
            "errors": errors,
        }

    async def _execute_cleanup(
        self,
        session: AsyncSession,
        pair: DuplicatePair,
        winner: DuplicateRecord,
        loser: DuplicateRecord,
        dry_run: bool,
        force_delete: bool,
    ) -> dict[str, Any]:
        """Internal worker logic for checking qBittorrent, hardlinks, and executing deletion."""
        loser_path = loser.file_path
        torrent_hash = loser.torrent_hash

        # Step 1: Detect torrent if not already recorded
        if not torrent_hash and self.services.qbittorrent.is_configured:
            try:
                t = await self.services.qbittorrent.find_torrent_by_file_path(loser_path, deep_search=True)
                if t:
                    torrent_hash = t.get("hash")
                    loser.torrent_hash = torrent_hash
            except Exception as e:
                logger.debug("qBittorrent lookup failed: %s", e)

        # Step 2: Handle Torrent-backed file
        if torrent_hash and self.services.qbittorrent.is_configured and not force_delete:
            seed_info = await self.services.qbittorrent.get_torrent_seeding_info(
                torrent_hash=torrent_hash,
                min_ratio=self.settings.MIN_SEED_RATIO,
                min_days=self.settings.MIN_SEED_DAYS,
            )

            # If seeding rules are met, we can fully purge
            if seed_info["can_delete"]:
                if dry_run:
                    pair.status = DuplicatePairStatus.APPROVED
                    pair.action_taken = ActionTaken.NONE
                    return {
                        "success": True,
                        "dry_run": True,
                        "action": "Would delete torrent and underlying data (seeding requirements met)",
                        "space_saved": loser.file_size_bytes,
                    }

                # Real deletion of torrent + files
                await self.services.qbittorrent.delete_torrent(torrent_hash, delete_files=True)

                # Ensure library-side file is also deleted if it still exists on disk
                if os.path.exists(loser_path) and HardlinkUtils.is_safe_file_path(loser_path):
                    try:
                        os.remove(loser_path)
                        logger.info("Deleted library file after torrent purge: %s", loser_path)
                    except Exception as rm_err:
                        logger.debug("Library file already unlinked or could not be removed: %s", rm_err)

                # Remove from Radarr/Sonarr tracking
                if loser.media_type == "movie" and loser.radarr_id and self.services.radarr.is_configured:
                    try:
                        files = await self.services.radarr.get_movie_files(loser.radarr_id)
                        for f in files:
                            if f.get("path") == loser_path:
                                await self.services.radarr.delete_movie_file(f["id"])
                                break
                    except Exception as e:
                        logger.warning("Radarr file un-track failed: %s", e)
                elif loser.media_type == "episode" and loser.sonarr_id and self.services.sonarr.is_configured:
                    try:
                        files = await self.services.sonarr.get_episode_files(loser.sonarr_id)
                        for f in files:
                            if f.get("path") == loser_path:
                                await self.services.sonarr.delete_episode_file(f["id"])
                                break
                    except Exception as e:
                        logger.warning("Sonarr episode file un-track failed: %s", e)

                pair.status = DuplicatePairStatus.COMPLETED
                pair.action_taken = ActionTaken.DELETED
                pair.resolved_at = _utcnow()
                await self._post_cleanup_reconcile(winner, loser)

                return {
                    "success": True,
                    "action": "Deleted torrent and file (seeding requirements met)",
                    "space_saved": loser.file_size_bytes,
                }

            # Seeding rules NOT met yet: check hardlink status
            is_hl = HardlinkUtils.is_hardlinked(loser_path) if os.path.exists(loser_path) else loser.is_hardlinked

            if is_hl:
                # Remove library-side hardlink only! The download side file stays seeding intact.
                if dry_run:
                    pair.status = DuplicatePairStatus.APPROVED
                    pair.action_taken = ActionTaken.NONE
                    return {
                        "success": True,
                        "dry_run": True,
                        "action": "Would unlink library hardlink and place torrent into seed-lock queue",
                        "space_saved": 0,
                    }

                unlink_res = HardlinkUtils.safe_remove_library_hardlink(loser_path)
                if not unlink_res["removed"]:
                    pair.status = DuplicatePairStatus.ERROR
                    return {"success": False, "error": unlink_res.get("error")}

                # Create SeedLockEntry
                seed_entry = SeedLockEntry(
                    duplicate_pair_id=pair.id,
                    torrent_hash=torrent_hash,
                    torrent_name=seed_info.get("name") or os.path.basename(loser_path),
                    file_path=loser_path,
                    current_ratio=seed_info.get("ratio", 0.0),
                    target_ratio=self.settings.MIN_SEED_RATIO,
                    current_seed_days=int(seed_info.get("seeding_time_days", 0)),
                    target_seed_days=self.settings.MIN_SEED_DAYS,
                    status=SeedLockStatus.SEEDING,
                    created_at=_utcnow(),
                )
                session.add(seed_entry)

                pair.status = DuplicatePairStatus.SEED_LOCKED
                pair.action_taken = ActionTaken.HARDLINK_REMOVED
                await self._post_cleanup_reconcile(winner, loser)

                return {
                    "success": True,
                    "action": "Library hardlink removed; torrent queued in Seed-Lock until ratio/time met",
                    "space_saved": 0,
                    "seed_locked": True,
                }
            else:
                # Not a hardlink, cannot unlink without killing seed data. Place in seed-lock directly.
                seed_entry = SeedLockEntry(
                    duplicate_pair_id=pair.id,
                    torrent_hash=torrent_hash,
                    torrent_name=seed_info.get("name") or os.path.basename(loser_path),
                    file_path=loser_path,
                    current_ratio=seed_info.get("ratio", 0.0),
                    target_ratio=self.settings.MIN_SEED_RATIO,
                    current_seed_days=int(seed_info.get("seeding_time_days", 0)),
                    target_seed_days=self.settings.MIN_SEED_DAYS,
                    status=SeedLockStatus.SEEDING,
                    created_at=_utcnow(),
                )
                session.add(seed_entry)
                pair.status = DuplicatePairStatus.SEED_LOCKED
                pair.action_taken = ActionTaken.SEED_LOCK_QUEUED

                return {
                    "success": True,
                    "action": "Torrent placed into Seed-Lock queue (retention requirements active)",
                    "space_saved": 0,
                    "seed_locked": True,
                }

        # Step 3: Non-torrent backed file (Usenet / SABnzbd or raw file) OR forced deletion
        if not HardlinkUtils.is_safe_file_path(loser_path):
            logger.error("Security refusal: path %s is forbidden or unsafe for deletion", loser_path)
            pair.status = DuplicatePairStatus.ERROR
            return {"success": False, "error": f"Refusing to delete unsafe or system path: {loser_path}"}

        if dry_run:
            pair.status = DuplicatePairStatus.APPROVED
            pair.action_taken = ActionTaken.NONE
            return {
                "success": True,
                "dry_run": True,
                "action": f"Would delete file on disk: {loser_path}",
                "space_saved": loser.file_size_bytes,
            }

        # Real deletion
        file_deleted = False
        if os.path.exists(loser_path):
            try:
                os.remove(loser_path)
                file_deleted = True
                logger.info("Deleted file from disk: %s", loser_path)
            except Exception as e:
                logger.error("Failed to delete file %s: %s", loser_path, e)
                pair.status = DuplicatePairStatus.ERROR
                return {"success": False, "error": f"Failed to delete {loser_path}: {e}"}

        # Remove from Radarr/Sonarr tracking
        if loser.media_type == "movie" and loser.radarr_id and self.services.radarr.is_configured:
            try:
                files = await self.services.radarr.get_movie_files(loser.radarr_id)
                for f in files:
                    if f.get("path") == loser_path:
                        await self.services.radarr.delete_movie_file(f["id"])
                        break
            except Exception as e:
                logger.warning("Radarr file un-track failed: %s", e)
        elif loser.media_type == "episode" and loser.sonarr_id and self.services.sonarr.is_configured:
            try:
                files = await self.services.sonarr.get_episode_files(loser.sonarr_id)
                for f in files:
                    if f.get("path") == loser_path:
                        await self.services.sonarr.delete_episode_file(f["id"])
                        break
            except Exception as e:
                logger.warning("Sonarr file un-track failed: %s", e)

        pair.status = DuplicatePairStatus.COMPLETED
        pair.action_taken = ActionTaken.DELETED
        pair.resolved_at = _utcnow()

        await self._post_cleanup_reconcile(winner, loser)

        return {
            "success": True,
            "action": f"Deleted duplicate file ({loser.file_size_bytes} bytes)",
            "space_saved": loser.file_size_bytes,
        }

    async def _post_cleanup_reconcile(self, winner: DuplicateRecord, loser: DuplicateRecord) -> None:
        """Trigger post-cleanup sync: Plex refresh, Overseerr availability, Arr rescan."""
        # 1. Plex Refresh
        if self.services.plex.is_configured and winner.plex_rating_key:
            try:
                await self.services.plex.refresh_item(winner.plex_rating_key)
            except Exception as e:
                logger.debug("Plex item refresh skipped: %s", e)

        # 2. Overseerr Availability
        if self.services.overseerr.is_configured and winner.tmdb_id:
            try:
                media = await self.services.overseerr.get_media_by_tmdb(winner.tmdb_id)
                if media and media.get("id"):
                    # Mark status 5 = AVAILABLE
                    await self.services.overseerr.update_media_status(media["id"], status=5)
            except Exception as e:
                logger.debug("Overseerr sync failed: %s", e)

        # 3. Radarr / Sonarr rescan
        if winner.media_type == "movie" and winner.radarr_id and self.services.radarr.is_configured:
            try:
                await self.services.radarr.rescan_movie(winner.radarr_id)
            except Exception as e:
                logger.debug("Radarr rescan failed: %s", e)
        elif winner.media_type == "episode" and winner.sonarr_id and self.services.sonarr.is_configured:
            try:
                await self.services.sonarr.rescan_series(winner.sonarr_id)
            except Exception as e:
                logger.debug("Sonarr rescan failed: %s", e)
