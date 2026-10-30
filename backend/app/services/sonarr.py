"""Sonarr API client.

Provides methods to query the Sonarr TV library, retrieve episode file
metadata, custom format scores, and manage episode files.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SonarrEpisodeFile:
    """Simplified representation of a Sonarr episode file."""

    id: int
    series_id: int
    season_number: int
    episode_numbers: list[int]
    tvdb_id: int | None
    title: str
    series_title: str
    file_path: str | None
    file_size: int
    quality_name: str | None
    custom_format_score: int


class SonarrClient:
    """Async client for the Sonarr v3 API."""

    def __init__(self, url: str | None = None, apikey: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (url or settings.SONARR_URL).rstrip("/")
        self.apikey = apikey or settings.SONARR_APIKEY
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        """Return True if Sonarr connection details are set."""
        return bool(self.base_url and self.apikey)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"X-Api-Key": self.apikey},
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def test_connection(self) -> dict[str, Any]:
        """Test the connection and return service info."""
        if not self.is_configured:
            return {"ok": False, "error": "Sonarr URL or API key not configured"}
        try:
            client = await self._get_client()
            resp = await client.get("/api/v3/system/status")
            resp.raise_for_status()
            data = resp.json()
            return {
                "ok": True,
                "version": data.get("version", "unknown"),
                "name": "Sonarr",
            }
        except Exception as exc:
            logger.warning("Sonarr connection test failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def get_series(self) -> list[dict[str, Any]]:
        """Return all series from Sonarr."""
        client = await self._get_client()
        resp = await client.get("/api/v3/series")
        resp.raise_for_status()
        return resp.json()

    async def get_series_by_id(self, series_id: int) -> dict[str, Any]:
        """Return a single series by Sonarr ID."""
        client = await self._get_client()
        resp = await client.get(f"/api/v3/series/{series_id}")
        resp.raise_for_status()
        return resp.json()

    async def get_episode_files(self, series_id: int) -> list[dict[str, Any]]:
        """Return all episode files for a given series."""
        client = await self._get_client()
        resp = await client.get("/api/v3/episodefile", params={"seriesId": series_id})
        resp.raise_for_status()
        return resp.json()

    async def get_episodes(self, series_id: int) -> list[dict[str, Any]]:
        """Return all episodes for a given series."""
        client = await self._get_client()
        resp = await client.get("/api/v3/episode", params={"seriesId": series_id})
        resp.raise_for_status()
        return resp.json()

    async def delete_episode_file(self, file_id: int) -> bool:
        """Delete an episode file by ID.

        Args:
            file_id: The Sonarr episode file ID.

        Returns:
            True if deletion was successful.
        """
        client = await self._get_client()
        resp = await client.delete(f"/api/v3/episodefile/{file_id}")
        resp.raise_for_status()
        logger.info("Deleted Sonarr episode file %d", file_id)
        return True

    async def get_quality_profiles(self) -> list[dict[str, Any]]:
        """Return all quality profiles."""
        client = await self._get_client()
        resp = await client.get("/api/v3/qualityprofile")
        resp.raise_for_status()
        return resp.json()

    async def get_queue(self) -> list[dict[str, Any]]:
        """Return the current download queue."""
        client = await self._get_client()
        resp = await client.get(
            "/api/v3/queue",
            params={"page": 1, "pageSize": 500, "includeUnknownSeriesItems": False},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("records", [])

    async def get_custom_formats(self) -> list[dict[str, Any]]:
        """Return all custom formats."""
        client = await self._get_client()
        resp = await client.get("/api/v3/customformat")
        resp.raise_for_status()
        return resp.json()

    async def delete_queue_item(
        self, queue_id: int, remove_from_client: bool = True, blocklist: bool = False
    ) -> bool:
        """Remove item from download queue, optionally adding to blocklist."""
        client = await self._get_client()
        resp = await client.delete(
            f"/api/v3/queue/{queue_id}",
            params={
                "removeFromClient": str(remove_from_client).lower(),
                "blocklist": str(blocklist).lower(),
            },
        )
        resp.raise_for_status()
        return True

    async def rescan_series(self, series_id: int) -> dict[str, Any]:
        """Trigger a disk rescan command for a specific series."""
        client = await self._get_client()
        resp = await client.post(
            "/api/v3/command",
            json={"name": "RescanSeries", "seriesId": series_id},
        )
        resp.raise_for_status()
        return resp.json()
