"""SABnzbd API client.

Provides methods to interact with the SABnzbd Usenet download client
for queue inspection and history queries.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class SABnzbdClient:
    """Async client for the SABnzbd API."""

    def __init__(self, url: str | None = None, apikey: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (url or settings.SABNZBD_URL).rstrip("/")
        self.apikey = apikey or settings.SABNZBD_APIKEY
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        """Return True if SABnzbd connection details are set."""
        return bool(self.base_url and self.apikey)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _api_call(self, mode: str, **kwargs: Any) -> dict[str, Any]:
        """Make a SABnzbd API call.

        Args:
            mode: The SABnzbd API mode parameter.
            **kwargs: Additional query parameters.
        """
        client = await self._get_client()
        params: dict[str, Any] = {
            "mode": mode,
            "apikey": self.apikey,
            "output": "json",
            **kwargs,
        }
        resp = await client.get("/api", params=params)
        resp.raise_for_status()
        return resp.json()

    async def test_connection(self) -> dict[str, Any]:
        """Test the connection and return service info."""
        if not self.is_configured:
            return {"ok": False, "error": "SABnzbd URL or API key not configured"}
        try:
            data = await self._api_call("version")
            return {
                "ok": True,
                "version": data.get("version", "unknown"),
                "name": "SABnzbd",
            }
        except Exception as exc:
            logger.warning("SABnzbd connection test failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def get_queue(self) -> list[dict[str, Any]]:
        """Return the current download queue."""
        data = await self._api_call("queue")
        queue_data = data.get("queue", {})
        return queue_data.get("slots", [])

    async def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return download history.

        Args:
            limit: Maximum number of history entries to return.
        """
        data = await self._api_call("history", limit=limit)
        history = data.get("history", {})
        return history.get("slots", [])

    async def get_status(self) -> dict[str, Any]:
        """Return full server status."""
        data = await self._api_call("fullstatus")
        return data.get("status", {})

    async def cancel_download(self, nzo_id: str, del_files: bool = True) -> bool:
        """Cancel and remove an active or queued download."""
        try:
            await self._api_call("queue", name="delete", value=nzo_id, del_files="1" if del_files else "0")
            logger.info("Cancelled SABnzbd download: %s", nzo_id)
            return True
        except Exception as e:
            logger.error("Failed to cancel SABnzbd download %s: %s", nzo_id, e)
            return False
