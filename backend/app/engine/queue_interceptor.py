"""Queue interceptor worker preventing redundant downloads across Radarr, Sonarr, SABnzbd, and qBittorrent."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.engine.quality_scorer import (
    MediaQualityInfo,
    QualityScorer,
    QualityWeights,
)
from app.models.duplicate import DuplicateRecord
from app.services import ServiceManager, get_service_manager

logger = logging.getLogger("arrclean.engine.queue_interceptor")


class QueueInterceptor:
    """Interception worker that identifies and cancels redundant downloads."""

    def __init__(
        self,
        service_manager: ServiceManager | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        quality_scorer: QualityScorer | None = None,
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

    async def check_queues(self) -> dict[str, Any]:
        """Poll download queues and cancel downloads that do not beat existing library quality."""
        checked = 0
        cancelled = 0
        actions: list[dict[str, Any]] = []

        # 1. Check Radarr Queue
        if self.services.radarr.is_configured:
            radarr_res = await self._check_radarr_queue()
            checked += radarr_res["checked"]
            cancelled += radarr_res["cancelled"]
            actions.extend(radarr_res["actions"])

        # 2. Check Sonarr Queue
        if self.services.sonarr.is_configured:
            sonarr_res = await self._check_sonarr_queue()
            checked += sonarr_res["checked"]
            cancelled += sonarr_res["cancelled"]
            actions.extend(sonarr_res["actions"])

        return {
            "checked": checked,
            "cancelled": cancelled,
            "actions": actions,
        }

    async def _check_radarr_queue(self) -> dict[str, Any]:
        """Check Radarr queue items against on-disk movies."""
        checked = 0
        cancelled = 0
        actions: list[dict[str, Any]] = []

        try:
            queue_records = await self.services.radarr.get_queue()
            for item in queue_records:
                checked += 1
                movie_id = item.get("movieId")
                queue_id = item.get("id")
                title = item.get("title", "")

                if not movie_id or not queue_id:
                    continue

                movie = await self.services.radarr.get_movie(movie_id)
                if not movie or not movie.get("hasFile"):
                    continue

                movie_file = movie.get("movieFile", {})
                existing_quality_str = movie_file.get("quality", {}).get("quality", {}).get("name", "")
                existing_cf_score = movie.get("customFormatScore", 0)

                # Queue item quality
                queued_quality_str = item.get("quality", {}).get("quality", {}).get("name", "")
                queued_cf_score = item.get("customFormatScore", 0)

                existing_score = self.scorer.calculate_composite_score(
                    MediaQualityInfo(
                        resolution=self.scorer.parse_resolution(existing_quality_str),
                        hdr_format=self.scorer.parse_hdr_format(movie_file.get("edition", "")),
                        source_type=self.scorer.parse_source_type(existing_quality_str),
                        audio_codec=self.scorer.parse_audio_codec(""),
                        video_codec=self.scorer.parse_video_codec(""),
                        custom_format_score=existing_cf_score,
                    )
                )

                queued_score = self.scorer.calculate_composite_score(
                    MediaQualityInfo(
                        resolution=self.scorer.parse_resolution(queued_quality_str),
                        hdr_format=self.scorer.parse_hdr_format(""),
                        source_type=self.scorer.parse_source_type(queued_quality_str),
                        audio_codec=self.scorer.parse_audio_codec(""),
                        video_codec=self.scorer.parse_video_codec(""),
                        custom_format_score=queued_cf_score,
                    )
                )

                # If existing on-disk file is equal or better, cancel the queue item
                if existing_score >= queued_score:
                    logger.info(
                        "Cancelling redundant Radarr download: '%s' (Queue Score: %.1f <= Existing: %.1f)",
                        title,
                        queued_score,
                        existing_score,
                    )
                    if not self.settings.DRY_RUN:
                        await self.services.radarr.delete_queue_item(
                            queue_id=queue_id,
                            remove_from_client=True,
                            blocklist=True,
                        )

                    cancelled += 1
                    actions.append({
                        "service": "radarr",
                        "title": title,
                        "reason": f"Existing quality ({existing_score:.1f}) >= Queued ({queued_score:.1f})",
                        "cancelled": not self.settings.DRY_RUN,
                    })

        except Exception as e:
            logger.warning("Error inspecting Radarr download queue: %s", e)

        return {"checked": checked, "cancelled": cancelled, "actions": actions}

    async def _check_sonarr_queue(self) -> dict[str, Any]:
        """Check Sonarr queue items against on-disk episodes."""
        checked = 0
        cancelled = 0
        actions: list[dict[str, Any]] = []

        try:
            queue_records = await self.services.sonarr.get_queue()
            for item in queue_records:
                checked += 1
                queue_id = item.get("id")
                series_id = item.get("seriesId")
                title = item.get("title", "")

                if not queue_id or not series_id:
                    continue

                episode = item.get("episode", {})
                has_file = episode.get("hasFile", False)
                if not has_file:
                    continue

                ep_file_id = episode.get("episodeFileId")
                if not ep_file_id:
                    continue

                ep_files = await self.services.sonarr.get_episode_files(series_id)
                current_file = next((f for f in ep_files if f.get("id") == ep_file_id), None)
                if not current_file:
                    continue

                existing_quality_str = current_file.get("quality", {}).get("quality", {}).get("name", "")
                queued_quality_str = item.get("quality", {}).get("quality", {}).get("name", "")

                existing_score = self.scorer.calculate_composite_score(
                    MediaQualityInfo(
                        resolution=self.scorer.parse_resolution(existing_quality_str),
                        hdr_format=self.scorer.parse_hdr_format(""),
                        source_type=self.scorer.parse_source_type(existing_quality_str),
                        audio_codec=self.scorer.parse_audio_codec(""),
                        video_codec=self.scorer.parse_video_codec(""),
                    )
                )

                queued_score = self.scorer.calculate_composite_score(
                    MediaQualityInfo(
                        resolution=self.scorer.parse_resolution(queued_quality_str),
                        hdr_format=self.scorer.parse_hdr_format(""),
                        source_type=self.scorer.parse_source_type(queued_quality_str),
                        audio_codec=self.scorer.parse_audio_codec(""),
                        video_codec=self.scorer.parse_video_codec(""),
                    )
                )

                if existing_score >= queued_score:
                    logger.info(
                        "Cancelling redundant Sonarr download: '%s' (Queue Score: %.1f <= Existing: %.1f)",
                        title,
                        queued_score,
                        existing_score,
                    )
                    if not self.settings.DRY_RUN:
                        await self.services.sonarr.delete_queue_item(
                            queue_id=queue_id,
                            remove_from_client=True,
                            blocklist=True,
                        )

                    cancelled += 1
                    actions.append({
                        "service": "sonarr",
                        "title": title,
                        "reason": f"Existing quality ({existing_score:.1f}) >= Queued ({queued_score:.1f})",
                        "cancelled": not self.settings.DRY_RUN,
                    })

        except Exception as e:
            logger.warning("Error inspecting Sonarr download queue: %s", e)

        return {"checked": checked, "cancelled": cancelled, "actions": actions}
