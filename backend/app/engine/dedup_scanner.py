"""Duplicate detection scanner that orchestrates Plex, Radarr, and Sonarr inspection."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.engine.hardlink_utils import HardlinkUtils
from app.engine.media_inspector import MediaInspector
from app.engine.quality_scorer import (
    MediaQualityInfo,
    QualityScorer,
    QualityWeights,
    Resolution,
)
from app.engine.tv_parser import TVParser
from app.models.duplicate import (
    ActionTaken,
    DuplicatePair,
    DuplicatePairStatus,
    DuplicateRecord,
)
from app.models.job_history import JobStatus, JobType, ScanJob
from app.services import ServiceManager, get_service_manager

logger = logging.getLogger("arrclean.engine.dedup_scanner")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DedupScanner:
    """Scans media libraries and queues to detect duplicate files and evaluate quality."""

    def __init__(
        self,
        service_manager: ServiceManager | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        quality_scorer: QualityScorer | None = None,
        media_inspector: MediaInspector | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.services = service_manager or get_service_manager()
        self.session_factory = session_factory
        self.settings = settings or get_settings()

        weights = QualityWeights(
            resolution=self.settings.WEIGHT_RESOLUTION,
            hdr=self.settings.WEIGHT_HDR,
            source=self.settings.WEIGHT_SOURCE,
            audio=self.settings.WEIGHT_AUDIO,
            codec=self.settings.WEIGHT_CODEC,
        )
        self.scorer = quality_scorer or QualityScorer(weights=weights)
        self.inspector = media_inspector or MediaInspector()

    async def run_full_scan(self, job_type: JobType = JobType.FULL_SCAN) -> dict[str, Any]:
        """Execute a full deduplication scan across configured services.

        Steps:
        1. Initialize ScanJob in DB.
        2. Scan Plex movie & show libraries for duplicates.
        3. Cross-reference with Radarr and Sonarr for CF scores and profile ranks.
        4. Inspect file streams / metadata and score candidate files.
        5. Group candidates, evaluate winners/losers, and persist DuplicatePair records.
        6. Record job metrics and dispatch notifications.
        """
        if self.session_factory is None:
            from app.database import get_session_factory
            self.session_factory = get_session_factory()

        scan_job_id: int | None = None
        async with self.session_factory() as session:
            job = ScanJob(
                job_type=job_type,
                status=JobStatus.RUNNING,
                started_at=_utcnow(),
            )
            session.add(job)
            await session.commit()
            scan_job_id = job.id

        duplicates_found = 0
        duplicates_resolved = 0
        total_potential_savings = 0
        error_msg: str | None = None
        log_lines: list[str] = []

        try:
            log_lines.append(f"Starting scan (Job #{scan_job_id}) at {_utcnow().isoformat()}")

            # 0. Prune any previously saved invalid pairs with mismatched seasons/episodes
            async with self.session_factory() as session:
                existing_pending_stmt = (
                    select(DuplicatePair)
                    .where(DuplicatePair.status == DuplicatePairStatus.PENDING_REVIEW)
                )
                res = await session.execute(existing_pending_stmt)
                pending_pairs = list(res.scalars().all())
                pruned_count = 0
                for pp in pending_pairs:
                    w_rec = (await session.execute(select(DuplicateRecord).where(DuplicateRecord.id == pp.winner_record_id))).scalar_one_or_none()
                    l_rec = (await session.execute(select(DuplicateRecord).where(DuplicateRecord.id == pp.loser_record_id))).scalar_one_or_none()
                    if w_rec and l_rec:
                        cand_w = {"media_type": w_rec.media_type, "season": w_rec.season, "episode": w_rec.episode, "file_path": w_rec.file_path}
                        cand_l = {"media_type": l_rec.media_type, "season": l_rec.season, "episode": l_rec.episode, "file_path": l_rec.file_path}
                        if not TVParser.are_candidates_compatible(cand_w, cand_l):
                            await session.delete(pp)
                            pruned_count += 1
                if pruned_count > 0:
                    await session.commit()
                    log_lines.append(f"Pruned {pruned_count} invalid mismatched duplicate pairs from previous scans.")

            # 1. Scan Plex Movies & Radarr
            movie_pairs = await self._scan_movies(log_lines)

            # 2. Scan Plex Episodes & Sonarr
            episode_pairs = await self._scan_episodes(log_lines)

            all_pairs = movie_pairs + episode_pairs
            duplicates_found = len(all_pairs)

            # 3. Persist pairs in DB
            async with self.session_factory() as session:
                for pair_data in all_pairs:
                    winner_data = pair_data["winner"]
                    loser_data = pair_data["loser"]

                    # Check if an active pair for this loser file already exists
                    existing_stmt = (
                        select(DuplicatePair)
                        .join(DuplicateRecord, DuplicatePair.loser_record_id == DuplicateRecord.id)
                        .where(DuplicateRecord.file_path == loser_data["file_path"])
                        .where(
                            DuplicatePair.status.in_([
                                DuplicatePairStatus.PENDING_REVIEW,
                                DuplicatePairStatus.APPROVED,
                                DuplicatePairStatus.SEED_LOCKED,
                            ])
                        )
                    )
                    existing_pair = (await session.execute(existing_stmt)).scalar_one_or_none()
                    if existing_pair:
                        continue

                    total_potential_savings += pair_data.get("space_saved", 0)

                    # Create DuplicateRecord for winner
                    winner_rec = DuplicateRecord(**winner_data)
                    session.add(winner_rec)

                    # Create DuplicateRecord for loser
                    loser_rec = DuplicateRecord(**loser_data)
                    session.add(loser_rec)

                    await session.flush()

                    dup_pair = DuplicatePair(
                        media_type=pair_data["media_type"],
                        title=pair_data["title"],
                        tmdb_id=pair_data.get("tmdb_id"),
                        tvdb_id=pair_data.get("tvdb_id"),
                        winner_record_id=winner_rec.id,
                        loser_record_id=loser_rec.id,
                        status=DuplicatePairStatus.PENDING_REVIEW,
                        action_taken=ActionTaken.NONE,
                        space_saved_bytes=loser_rec.file_size_bytes,
                        created_at=_utcnow(),
                    )
                    session.add(dup_pair)

                await session.commit()

            log_lines.append(f"Scan complete. Found {duplicates_found} duplicate pairs.")

        except Exception as e:
            logger.exception("Error occurred during deduplication scan")
            error_msg = str(e)
            log_lines.append(f"ERROR: {error_msg}")

        # Update job record
        async with self.session_factory() as session:
            job_stmt = select(ScanJob).where(ScanJob.id == scan_job_id)
            res = await session.execute(job_stmt)
            job_rec = res.scalar_one_or_none()
            if job_rec:
                job_rec.status = JobStatus.FAILED if error_msg else JobStatus.COMPLETED
                job_rec.completed_at = _utcnow()
                job_rec.duplicates_found = duplicates_found
                job_rec.duplicates_resolved = duplicates_resolved
                job_rec.space_reclaimed_bytes = total_potential_savings
                job_rec.error_message = error_msg
                job_rec.log_output = "\n".join(log_lines)
                await session.commit()

        # Send notification
        if self.services.notifications.has_any_configured:
            try:
                await self.services.notifications.notify_scan_complete(
                    duplicates_found=duplicates_found,
                    duplicates_resolved=duplicates_resolved,
                    space_reclaimed_bytes=total_potential_savings,
                    error=error_msg,
                )
            except Exception as notify_err:
                logger.warning("Failed to dispatch scan notification: %s", notify_err)

        return {
            "job_id": scan_job_id,
            "status": "failed" if error_msg else "completed",
            "duplicates_found": duplicates_found,
            "space_reclaimed_bytes": total_potential_savings,
            "error": error_msg,
        }

    async def _scan_movies(self, log_lines: list[str]) -> list[dict[str, Any]]:
        """Find movie duplicates across Plex and Radarr."""
        pairs: list[dict[str, Any]] = []

        # Map movies by TMDB ID / Title from Plex
        plex_movie_groups: dict[str, list[dict[str, Any]]] = {}

        if self.services.plex.is_configured:
            try:
                libraries = await self.services.plex.get_libraries()
                movie_sections = [lib for lib in libraries if lib.get("type") == "movie"]

                for section in movie_sections:
                    sec_key = section.get("key", "")
                    items = await self.services.plex.get_library_items(sec_key)
                    for item in items:
                        # Items with multiple Media tags
                        media_list = item.get("Media", [])
                        if len(media_list) > 1:
                            key = f"plex_movie_{item.get('ratingKey')}"
                            parsed = self.services.plex.parse_media_item(item)
                            plex_movie_groups[key] = [
                                {
                                    "source": "plex",
                                    "title": p.title,
                                    "year": p.year,
                                    "file_path": p.file_path,
                                    "file_size": p.file_size,
                                    "resolution": p.resolution,
                                    "video_codec": p.video_codec,
                                    "audio_codec": p.audio_codec,
                                    "bitrate": p.bitrate,
                                    "plex_rating_key": p.rating_key,
                                }
                                for p in parsed
                                if p.file_path
                            ]
            except Exception as e:
                log_lines.append(f"Plex movie scan warning: {e}")

        # Also cross-check Radarr for movies with multiple files or orphaned files
        radarr_movie_map: dict[int, dict[str, Any]] = {}
        if self.services.radarr.is_configured:
            try:
                radarr_movies = await self.services.radarr.get_movies()
                for m in radarr_movies:
                    tmdb = m.get("tmdbId")
                    if tmdb:
                        radarr_movie_map[tmdb] = m

                    # Check if Radarr itself has multiple movie files
                    m_id = m.get("id")
                    if m_id and m.get("hasFile"):
                        files = await self.services.radarr.get_movie_files(m_id)
                        if len(files) > 1:
                            key = f"radarr_movie_{tmdb or m_id}"
                            if key not in plex_movie_groups:
                                plex_movie_groups[key] = [
                                    {
                                        "source": "radarr",
                                        "title": m.get("title", "Unknown"),
                                        "year": m.get("year"),
                                        "tmdb_id": tmdb,
                                        "radarr_id": m_id,
                                        "file_path": f.get("path", ""),
                                        "file_size": f.get("size", 0),
                                        "resolution": f.get("quality", {}).get("quality", {}).get("name"),
                                        "custom_format_score": f.get("customFormatScore", 0),
                                    }
                                    for f in files
                                    if f.get("path")
                                ]
            except Exception as e:
                log_lines.append(f"Radarr movie scan warning: {e}")

        # Process detected groups into DuplicatePairs
        for group_key, file_items in plex_movie_groups.items():
            if len(file_items) < 2:
                continue

            evaluated_candidates: list[dict[str, Any]] = []
            for item in file_items:
                f_path = item["file_path"]

                # MediaInspector fallback when stream attributes are unknown or basic SDR
                if os.path.exists(f_path) and (
                    not item.get("resolution")
                    or not item.get("hdr_format")
                    or item.get("hdr_format") == "SDR"
                    or not item.get("audio_codec")
                ):
                    try:
                        inspected = await self.inspector.inspect_file(f_path)
                        v_info = inspected.get("video", {})
                        if not item.get("resolution") or item.get("resolution") == "SD":
                            item["resolution"] = v_info.get("resolution")
                        if v_info.get("hdr_format") and v_info.get("hdr_format") != "SDR":
                            item["hdr_format"] = v_info.get("hdr_format")
                        if not item.get("video_codec") or item.get("video_codec") == "unknown":
                            item["video_codec"] = v_info.get("codec")
                        if not item.get("bitrate") and v_info.get("bitrate_kbps"):
                            item["bitrate"] = v_info.get("bitrate_kbps") * 1000
                        if inspected.get("audio_tracks") and not item.get("audio_codec"):
                            item["audio_codec"] = inspected["audio_tracks"][0].get("codec")
                    except Exception as inspect_err:
                        logger.debug("Media inspection fallback on %s: %s", f_path, inspect_err)

                # Extract or inspect technical details
                file_size = item.get("file_size") or (os.path.getsize(f_path) if os.path.exists(f_path) else 0)
                edition = self.scorer.parse_edition(os.path.basename(f_path))

                # Hardlink & Torrent info
                is_hl = HardlinkUtils.is_hardlinked(f_path) if os.path.exists(f_path) else False
                inode = HardlinkUtils.get_inode(f_path) if os.path.exists(f_path) else None

                t_hash: str | None = None
                if self.services.qbittorrent.is_configured:
                    try:
                        torrent = await self.services.qbittorrent.find_torrent_by_file_path(f_path)
                        if torrent:
                            t_hash = torrent.get("hash")
                    except Exception:
                        pass

                # CF score lookup from Radarr
                cf_score = item.get("custom_format_score")
                tmdb_id = item.get("tmdb_id")
                radarr_id = item.get("radarr_id")
                if tmdb_id and tmdb_id in radarr_movie_map:
                    rm = radarr_movie_map[tmdb_id]
                    cf_score = cf_score or rm.get("customFormatScore", 0)
                    radarr_id = radarr_id or rm.get("id")

                quality_info = MediaQualityInfo(
                    resolution=self.scorer.parse_resolution(item.get("resolution") or ""),
                    hdr_format=self.scorer.parse_hdr_format(item.get("hdr_format") or ""),
                    source_type=self.scorer.parse_source_type(os.path.basename(f_path)),
                    audio_codec=self.scorer.parse_audio_codec(item.get("audio_codec") or ""),
                    video_codec=self.scorer.parse_video_codec(item.get("video_codec") or ""),
                    video_bitrate_kbps=(item.get("bitrate") or 0) // 1000 if (item.get("bitrate") or 0) > 10000 else (item.get("bitrate") or 0),
                    custom_format_score=cf_score,
                    edition=edition,
                    file_size_bytes=file_size,
                )

                score = self.scorer.calculate_composite_score(quality_info)

                evaluated_candidates.append({
                    "record": {
                        "media_type": "movie",
                        "tmdb_id": tmdb_id,
                        "imdb_id": item.get("imdb_id"),
                        "title": item.get("title", "Unknown"),
                        "edition": edition or None,
                        "file_path": f_path,
                        "file_size_bytes": file_size,
                        "resolution": item.get("resolution") or quality_info.resolution.name,
                        "hdr_format": quality_info.hdr_format.name,
                        "source_type": quality_info.source_type.name,
                        "audio_codec": quality_info.audio_codec.name,
                        "video_codec": quality_info.video_codec.name,
                        "video_bitrate": quality_info.video_bitrate_kbps * 1000,
                        "custom_format_score": cf_score,
                        "composite_quality_score": score,
                        "plex_rating_key": item.get("plex_rating_key"),
                        "radarr_id": radarr_id,
                        "is_hardlinked": is_hl,
                        "inode_number": inode,
                        "torrent_hash": t_hash,
                    },
                    "quality_info": quality_info,
                    "score": score,
                })

            # Check Edition consolidation setting
            if not self.settings.EDITION_CONSOLIDATE:
                # Group by edition, only compare if same edition
                editions: dict[str, list[dict[str, Any]]] = {}
                for cand in evaluated_candidates:
                    ed = cand["record"]["edition"] or "default"
                    editions.setdefault(ed, []).append(cand)

                for ed_name, ed_candidates in editions.items():
                    if len(ed_candidates) >= 2:
                        pairs.extend(self._create_pairs_from_candidates(ed_candidates))
            else:
                pairs.extend(self._create_pairs_from_candidates(evaluated_candidates))

        return pairs

    async def _scan_episodes(self, log_lines: list[str]) -> list[dict[str, Any]]:
        """Find TV episode duplicates across Plex and Sonarr."""
        pairs: list[dict[str, Any]] = []

        # Find series in Sonarr and build lookup map
        sonarr_title_map: dict[str, dict[str, Any]] = {}
        if self.services.sonarr.is_configured:
            try:
                series_list = await self.services.sonarr.get_series()
                for s in series_list:
                    title_clean = s.get("title", "").strip().lower()
                    if title_clean:
                        sonarr_title_map[title_clean] = s
            except Exception as e:
                log_lines.append(f"Sonarr scan warning: {e}")

        # Scan Plex TV shows
        if self.services.plex.is_configured:
            try:
                libraries = await self.services.plex.get_libraries()
                show_sections = [lib for lib in libraries if lib.get("type") == "show"]

                for section in show_sections:
                    sec_key = section.get("key", "")
                    items = await self.services.plex.get_library_items(sec_key, item_type=4)

                    # Group episodes by title / detected season / detected episode
                    episode_groups: dict[str, list[dict[str, Any]]] = {}
                    for item in items:
                        if item.get("type") == "episode" and len(item.get("Media", [])) > 1:
                            show_title = item.get("grandparentTitle", item.get("title", "Unknown"))
                            fallback_season = item.get("parentIndex")
                            fallback_episode = item.get("index")

                            parsed = self.services.plex.parse_media_item(item)
                            for p in parsed:
                                if not p.file_path:
                                    continue

                                # Extract true season and episode from filename and directory
                                file_season, file_ep, _ = TVParser.parse_season_episode(
                                    p.file_path,
                                    fallback_season=fallback_season,
                                    fallback_episode=fallback_episode,
                                )

                                # Group strictly by show title + detected season + detected episode
                                key = f"{show_title.strip().lower()}_S{file_season}E{file_ep}"
                                episode_groups.setdefault(key, []).append({
                                    "title": f"{show_title} S{file_season:02d}E{file_ep:02d}" if file_season and file_ep else show_title,
                                    "show_title": show_title,
                                    "season": file_season,
                                    "episode": file_ep,
                                    "file_path": p.file_path,
                                    "file_size": p.file_size,
                                    "resolution": p.resolution,
                                    "video_codec": p.video_codec,
                                    "audio_codec": p.audio_codec,
                                    "duration_ms": p.duration_ms,
                                    "plex_rating_key": p.rating_key,
                                })

                    for ep_key, ep_files in episode_groups.items():
                        if len(ep_files) >= 2:
                            # Map Sonarr series if available
                            first_item = ep_files[0]
                            parsed_show = first_item.get("show_title", "").strip().lower()
                            sonarr_match = sonarr_title_map.get(parsed_show)
                            sonarr_id = sonarr_match.get("id") if sonarr_match else None
                            tvdb_id = sonarr_match.get("tvdbId") if sonarr_match else None

                            for ep in ep_files:
                                ep["sonarr_id"] = sonarr_id
                                ep["tvdb_id"] = tvdb_id

                            cands = await self._evaluate_episode_candidates(ep_files)
                            pairs.extend(self._create_pairs_from_candidates(cands))

            except Exception as e:
                log_lines.append(f"Plex episode scan warning: {e}")

        return pairs

    async def _evaluate_episode_candidates(self, ep_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Score a list of duplicate episode files."""
        cands: list[dict[str, Any]] = []
        for item in ep_files:
            f_path = item["file_path"]

            # MediaInspector fallback
            if os.path.exists(f_path) and (
                not item.get("resolution")
                or not item.get("hdr_format")
                or item.get("hdr_format") == "SDR"
                or not item.get("audio_codec")
            ):
                try:
                    inspected = await self.inspector.inspect_file(f_path)
                    v_info = inspected.get("video", {})
                    if not item.get("resolution") or item.get("resolution") == "SD":
                        item["resolution"] = v_info.get("resolution")
                    if v_info.get("hdr_format") and v_info.get("hdr_format") != "SDR":
                        item["hdr_format"] = v_info.get("hdr_format")
                    if not item.get("video_codec") or item.get("video_codec") == "unknown":
                        item["video_codec"] = v_info.get("codec")
                    if inspected.get("audio_tracks") and not item.get("audio_codec"):
                        item["audio_codec"] = inspected["audio_tracks"][0].get("codec")
                except Exception as inspect_err:
                    logger.debug("Media inspection fallback on %s: %s", f_path, inspect_err)

            file_size = item.get("file_size") or (os.path.getsize(f_path) if os.path.exists(f_path) else 0)

            is_hl = HardlinkUtils.is_hardlinked(f_path) if os.path.exists(f_path) else False
            inode = HardlinkUtils.get_inode(f_path) if os.path.exists(f_path) else None

            t_hash: str | None = None
            if self.services.qbittorrent.is_configured:
                try:
                    torrent = await self.services.qbittorrent.find_torrent_by_file_path(f_path)
                    if torrent:
                        t_hash = torrent.get("hash")
                except Exception:
                    pass

            quality_info = MediaQualityInfo(
                resolution=self.scorer.parse_resolution(item.get("resolution") or ""),
                hdr_format=self.scorer.parse_hdr_format(item.get("hdr_format") or ""),
                source_type=self.scorer.parse_source_type(os.path.basename(f_path)),
                audio_codec=self.scorer.parse_audio_codec(item.get("audio_codec") or ""),
                video_codec=self.scorer.parse_video_codec(item.get("video_codec") or ""),
                custom_format_score=item.get("custom_format_score", 0),
                file_size_bytes=file_size,
            )
            score = self.scorer.calculate_composite_score(quality_info)

            cands.append({
                "record": {
                    "media_type": "episode",
                    "title": item.get("title", "Unknown"),
                    "tvdb_id": item.get("tvdb_id"),
                    "sonarr_id": item.get("sonarr_id"),
                    "season": item.get("season"),
                    "episode": item.get("episode"),
                    "file_path": f_path,
                    "file_size_bytes": file_size,
                    "resolution": item.get("resolution") or quality_info.resolution.name,
                    "hdr_format": quality_info.hdr_format.name,
                    "source_type": quality_info.source_type.name,
                    "audio_codec": quality_info.audio_codec.name,
                    "video_codec": quality_info.video_codec.name,
                    "composite_quality_score": score,
                    "plex_rating_key": item.get("plex_rating_key"),
                    "is_hardlinked": is_hl,
                    "inode_number": inode,
                    "torrent_hash": t_hash,
                },
                "quality_info": quality_info,
                "score": score,
            })
        return cands

    def _create_pairs_from_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sort candidates by score descending and return (winner, loser) pairs."""
        if len(candidates) < 2:
            return []

        # Highest score is winner
        sorted_cands = sorted(candidates, key=lambda c: c["score"], reverse=True)
        winner = sorted_cands[0]
        losers = sorted_cands[1:]

        pairs: list[dict[str, Any]] = []
        for loser in losers:
            # Enforce strict compatibility: never pair mismatched seasons, episodes, or divergent durations
            if not TVParser.are_candidates_compatible(winner["record"], loser["record"]):
                logger.warning(
                    "Rejected incompatible duplicate pair: '%s' vs '%s'",
                    winner["record"].get("file_path"),
                    loser["record"].get("file_path"),
                )
                continue

            pairs.append({
                "media_type": winner["record"]["media_type"],
                "title": winner["record"]["title"],
                "tmdb_id": winner["record"].get("tmdb_id"),
                "tvdb_id": winner["record"].get("tvdb_id"),
                "winner": winner["record"],
                "loser": loser["record"],
                "space_saved": loser["record"]["file_size_bytes"],
            })
        return pairs
