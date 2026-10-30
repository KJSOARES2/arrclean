"""Overseerr / Jellyseerr API client.

Provides methods to query media requests and availability status,
which is useful for understanding why duplicate copies may exist.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class OverseerrClient:
    """Async client for the Overseerr / Jellyseerr API."""

    def __init__(self, url: str | None = None, apikey: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (url or settings.OVERSEERR_URL).rstrip("/")
        raw_key = apikey if (apikey and "•" not in apikey and apikey != "••••••••") else settings.OVERSEERR_APIKEY
        self.apikey = raw_key.strip() if raw_key else ""
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        """Return True if Overseerr connection details are set."""
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
            return {"ok": False, "error": "Overseerr URL or API key not configured"}
        try:
            client = await self._get_client()
            resp = await client.get("/api/v1/status")
            resp.raise_for_status()
            data = resp.json()
            return {
                "ok": True,
                "version": data.get("version", "unknown"),
                "name": "Overseerr",
            }
        except Exception as exc:
            logger.warning("Overseerr connection test failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def get_requests(
        self, take: int = 50, skip: int = 0, status: str = "approved"
    ) -> dict[str, Any]:
        """Return media requests.

        Args:
            take: Number of results to return.
            skip: Number of results to skip.
            status: Filter by status (approved, pending, declined, etc.).
        """
        client = await self._get_client()
        resp = await client.get(
            "/api/v1/request",
            params={"take": take, "skip": skip, "filter": status},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_media(self, media_id: int) -> dict[str, Any]:
        """Return media details by ID."""
        client = await self._get_client()
        resp = await client.get(f"/api/v1/media/{media_id}")
        resp.raise_for_status()
        return resp.json()

    async def search(self, query: str) -> list[dict[str, Any]]:
        """Search for media.

        Args:
            query: Search query string.
        """
        client = await self._get_client()
        resp = await client.get(
            "/api/v1/search", params={"query": query, "page": 1, "language": "en"}
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])

    async def get_media_by_tmdb(self, tmdb_id: int) -> dict[str, Any] | None:
        """Find media status by TMDB ID."""
        client = await self._get_client()
        try:
            resp = await client.get(f"/api/v1/movie/{tmdb_id}")
            resp.raise_for_status()
            data = resp.json()
            return data.get("mediaInfo")
        except Exception:
            return None

    async def update_media_status(
        self, media_id: int, status: int | str = "available", is4k: bool = False
    ) -> bool:
        """Update media availability status (e.g. 'available', 'partial', 'processing')."""
        client = await self._get_client()
        status_map = {
            1: "unknown",
            2: "pending",
            3: "processing",
            4: "partial",
            5: "available",
        }
        if isinstance(status, int):
            status_str = status_map.get(status, "available")
        else:
            status_str = str(status).lower()

        try:
            body = {"is4k": is4k} if is4k else None
            resp = await client.post(
                f"/api/v1/media/{media_id}/{status_str}",
                json=body,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("Failed to update Overseerr status for media %d: %s", media_id, e)
            return False
