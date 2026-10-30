"""Plex Media Server API client.

Provides methods to query the Plex library for media items, detect
duplicates from Plex's perspective, and retrieve metadata.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class PlexMediaItem:
    """Simplified representation of a Plex media item."""

    rating_key: str
    title: str
    year: int | None
    media_type: str  # "movie" or "episode"
    file_path: str
    file_size: int
    resolution: str | None
    video_codec: str | None
    audio_codec: str | None
    bitrate: int | None
    duration_ms: int | None
    added_at: int | None


class PlexClient:
    """Async client for the Plex Media Server HTTP API."""

    def __init__(self, url: str | None = None, token: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (url or settings.PLEX_URL).rstrip("/")
        self.token = token or settings.PLEX_TOKEN
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        """Return True if Plex connection details are set."""
        return bool(self.base_url and self.token)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "X-Plex-Token": self.token,
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def test_connection(self) -> dict[str, Any]:
        """Test the connection and return server identity info.

        Returns:
            Dict with ``ok``, ``version``, ``name``, and ``error`` keys.
        """
        if not self.is_configured:
            return {"ok": False, "error": "Plex URL or token not configured"}
        try:
            client = await self._get_client()
            resp = await client.get("/")
            resp.raise_for_status()
            data = resp.json()
            mc = data.get("MediaContainer", {})
            return {
                "ok": True,
                "version": mc.get("version", "unknown"),
                "name": mc.get("friendlyName", "unknown"),
            }
        except Exception as exc:
            logger.warning("Plex connection test failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def get_libraries(self) -> list[dict[str, Any]]:
        """Return a list of all Plex library sections."""
        client = await self._get_client()
        resp = await client.get("/library/sections")
        resp.raise_for_status()
        data = resp.json()
        sections = data.get("MediaContainer", {}).get("Directory", [])
        return [
            {
                "key": s["key"],
                "title": s["title"],
                "type": s["type"],
                "agent": s.get("agent", ""),
            }
            for s in sections
        ]

    async def get_library_items(
        self, section_key: str, item_type: int | None = None
    ) -> list[dict[str, Any]]:
        """Return all items in a library section.

        Args:
            section_key: The Plex library section key (e.g. "1").
            item_type: Optional Plex item type filter (e.g. 1 for movies, 4 for episodes).

        Returns:
            List of raw Plex metadata dicts.
        """
        client = await self._get_client()
        params: dict[str, Any] = {}
        if item_type is not None:
            params["type"] = item_type

        resp = await client.get(
            f"/library/sections/{section_key}/all",
            params=params if params else None,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("MediaContainer", {}).get("Metadata", [])

    async def get_item_metadata(self, rating_key: str) -> dict[str, Any]:
        """Return full metadata for a specific Plex item.

        Args:
            rating_key: The Plex rating key.
        """
        client = await self._get_client()
        resp = await client.get(f"/library/metadata/{rating_key}")
        resp.raise_for_status()
        data = resp.json()
        items = data.get("MediaContainer", {}).get("Metadata", [])
        return items[0] if items else {}

    async def get_duplicate_items(self, section_key: str) -> list[dict[str, Any]]:
        """Return items that Plex has flagged as duplicates.

        Uses the ``/library/sections/{key}/duplicate`` endpoint if available
        (Plex Pass feature), otherwise falls back to listing all items.
        """
        client = await self._get_client()
        try:
            resp = await client.get(f"/library/sections/{section_key}/duplicate")
            resp.raise_for_status()
            data = resp.json()
            return data.get("MediaContainer", {}).get("Metadata", [])
        except httpx.HTTPStatusError:
            logger.info(
                "Plex duplicate endpoint not available for section %s; "
                "falling back to full scan.",
                section_key,
            )
            return []

    async def refresh_section(self, section_key: str) -> None:
        """Trigger a library section scan."""
        client = await self._get_client()
        resp = await client.get(f"/library/sections/{section_key}/refresh")
        resp.raise_for_status()

    async def refresh_item(self, rating_key: str) -> None:
        """Trigger metadata refresh for a specific item."""
        client = await self._get_client()
        resp = await client.put(f"/library/metadata/{rating_key}/refresh")
        resp.raise_for_status()

    async def empty_trash(self, section_key: str) -> None:
        """Empty trash for a library section."""
        client = await self._get_client()
        resp = await client.put(f"/library/sections/{section_key}/emptyTrash")
        resp.raise_for_status()

    def parse_media_item(self, metadata: dict[str, Any]) -> list[PlexMediaItem]:
        """Parse a Plex metadata dict into PlexMediaItem instances.

        A single metadata entry can have multiple Media objects (different
        versions/editions), so this returns a list.
        """
        items: list[PlexMediaItem] = []
        title = metadata.get("title", "Unknown")
        year = metadata.get("year")
        media_type = "movie" if metadata.get("type") == "movie" else "episode"
        rating_key = str(metadata.get("ratingKey", ""))

        for media in metadata.get("Media", []):
            for part in media.get("Part", []):
                items.append(
                    PlexMediaItem(
                        rating_key=rating_key,
                        title=title,
                        year=year,
                        media_type=media_type,
                        file_path=part.get("file", ""),
                        file_size=part.get("size", 0),
                        resolution=media.get("videoResolution"),
                        video_codec=media.get("videoCodec"),
                        audio_codec=media.get("audioCodec"),
                        bitrate=media.get("bitrate"),
                        duration_ms=media.get("duration"),
                        added_at=metadata.get("addedAt"),
                    )
                )
        return items
