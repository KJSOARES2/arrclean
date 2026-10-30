"""Radarr API client.

Provides methods to query the Radarr movie library, retrieve file metadata,
custom format scores, and manage movie files.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class RadarrMovie:
    """Simplified representation of a Radarr movie."""

    id: int
    tmdb_id: int
    imdb_id: str | None
    title: str
    year: int | None
    file_path: str | None
    file_size: int
    quality_name: str | None
    quality_revision: int
    custom_format_score: int
    edition: str | None
    has_file: bool


class RadarrClient:
    """Async client for the Radarr v3 API."""

    def __init__(self, url: str | None = None, apikey: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (url or settings.RADARR_URL).rstrip("/")
        self.apikey = apikey or settings.RADARR_APIKEY
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        """Return True if Radarr connection details are set."""
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
            return {"ok": False, "error": "Radarr URL or API key not configured"}
        try:
            client = await self._get_client()
            resp = await client.get("/api/v3/system/status")
            resp.raise_for_status()
            data = resp.json()
            return {
                "ok": True,
                "version": data.get("version", "unknown"),
                "name": "Radarr",
            }
        except Exception as exc:
            logger.warning("Radarr connection test failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def get_movies(self) -> list[dict[str, Any]]:
        """Return all movies from Radarr."""
        client = await self._get_client()
        resp = await client.get("/api/v3/movie")
        resp.raise_for_status()
        return resp.json()

    async def get_movie(self, movie_id: int) -> dict[str, Any]:
        """Return a single movie by Radarr ID."""
        client = await self._get_client()
        resp = await client.get(f"/api/v3/movie/{movie_id}")
        resp.raise_for_status()
        return resp.json()

    async def get_movie_files(self, movie_id: int) -> list[dict[str, Any]]:
        """Return all movie files for a given movie."""
        client = await self._get_client()
        resp = await client.get("/api/v3/moviefile", params={"movieId": movie_id})
        resp.raise_for_status()
        return resp.json()

    async def delete_movie_file(self, file_id: int) -> bool:
        """Delete a movie file by ID.

        Args:
            file_id: The Radarr movie file ID.

        Returns:
            True if deletion was successful.
        """
        client = await self._get_client()
        resp = await client.delete(f"/api/v3/moviefile/{file_id}")
        resp.raise_for_status()
        logger.info("Deleted Radarr movie file %d", file_id)
        return True

    async def get_quality_profiles(self) -> list[dict[str, Any]]:
        """Return all quality profiles."""
        client = await self._get_client()
        resp = await client.get("/api/v3/qualityprofile")
        resp.raise_for_status()
        return resp.json()

    async def get_custom_formats(self) -> list[dict[str, Any]]:
        """Return all custom format definitions."""
        client = await self._get_client()
        resp = await client.get("/api/v3/customformat")
        resp.raise_for_status()
        return resp.json()

    async def get_queue(self) -> list[dict[str, Any]]:
        """Return the current download queue."""
        client = await self._get_client()
        resp = await client.get(
            "/api/v3/queue",
            params={"page": 1, "pageSize": 500, "includeUnknownMovieItems": False},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("records", [])

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

    async def rescan_movie(self, movie_id: int) -> dict[str, Any]:
        """Trigger a disk rescan command for a specific movie."""
        client = await self._get_client()
        resp = await client.post(
            "/api/v3/command",
            json={"name": "RescanMovie", "movieId": movie_id},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_history(self, movie_id: int) -> list[dict[str, Any]]:
        """Return grab/import history for a specific movie."""
        client = await self._get_client()
        resp = await client.get(f"/api/v3/history/movie", params={"movieId": movie_id})
        resp.raise_for_status()
        return resp.json()

    async def unmonitor_movie(self, movie_id: int) -> None:
        """Set a movie's monitored state to False."""
        movie = await self.get_movie(movie_id)
        if not movie:
            return
        movie["monitored"] = False
        client = await self._get_client()
        resp = await client.put(f"/api/v3/movie/{movie_id}", json=movie)
        resp.raise_for_status()

    def parse_movie(self, data: dict[str, Any]) -> RadarrMovie:
        """Parse a raw Radarr movie dict into a RadarrMovie."""
        movie_file = data.get("movieFile", {})
        quality = movie_file.get("quality", {}).get("quality", {})
        return RadarrMovie(
            id=data.get("id", 0),
            tmdb_id=data.get("tmdbId", 0),
            imdb_id=data.get("imdbId"),
            title=data.get("title", "Unknown"),
            year=data.get("year"),
            file_path=movie_file.get("path"),
            file_size=movie_file.get("size", 0),
            quality_name=quality.get("name"),
            quality_revision=movie_file.get("quality", {}).get("revision", {}).get("version", 1),
            custom_format_score=data.get("customFormatScore", 0),
            edition=movie_file.get("edition"),
            has_file=data.get("hasFile", False),
        )
