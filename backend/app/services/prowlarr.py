"""Prowlarr API client.

Provides methods to query indexer status and proxy searches through
Prowlarr, which aggregates indexer results for the *arr suite.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class ProwlarrClient:
    """Async client for the Prowlarr API."""

    def __init__(self, url: str | None = None, apikey: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (url or settings.PROWLARR_URL).rstrip("/")
        raw_key = apikey if (apikey and "•" not in apikey and apikey != "••••••••") else settings.PROWLARR_APIKEY
        self.apikey = raw_key.strip() if raw_key else ""
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        """Return True if Prowlarr connection details are set."""
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
            return {"ok": False, "error": "Prowlarr URL or API key not configured"}
        try:
            client = await self._get_client()
            resp = await client.get("/api/v1/system/status")
            resp.raise_for_status()
            data = resp.json()
            return {
                "ok": True,
                "version": data.get("version", "unknown"),
                "name": "Prowlarr",
            }
        except Exception as exc:
            logger.warning("Prowlarr connection test failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def get_indexers(self) -> list[dict[str, Any]]:
        """Return all configured indexers."""
        client = await self._get_client()
        resp = await client.get("/api/v1/indexer")
        resp.raise_for_status()
        return resp.json()

    async def get_indexer_stats(self) -> dict[str, Any]:
        """Return indexer statistics."""
        client = await self._get_client()
        resp = await client.get("/api/v1/indexerstats")
        resp.raise_for_status()
        return resp.json()

    async def search(
        self, query: str, indexer_ids: list[int] | None = None
    ) -> list[dict[str, Any]]:
        """Search across indexers.

        Args:
            query: Search query.
            indexer_ids: Optional list of indexer IDs to search.
        """
        client = await self._get_client()
        params: dict[str, Any] = {"query": query, "type": "search"}
        if indexer_ids:
            params["indexerIds"] = indexer_ids
        resp = await client.get("/api/v1/search", params=params)
        resp.raise_for_status()
        return resp.json()
