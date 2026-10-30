"""qBittorrent Web API client.

Provides methods to authenticate with qBittorrent, list torrents,
query seeding status, and manage torrent files.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class TorrentInfo:
    """Simplified representation of a qBittorrent torrent."""

    hash: str
    name: str
    save_path: str
    size: int
    ratio: float
    seeding_time: int  # seconds
    state: str
    category: str
    tags: str
    added_on: int  # unix timestamp
    content_path: str


class QBittorrentClient:
    """Async client for the qBittorrent Web API v2."""

    def __init__(
        self,
        url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (url or settings.QBITTORRENT_URL).rstrip("/")
        self.username = username or settings.QBITTORRENT_USERNAME
        self.password = password or settings.QBITTORRENT_PASSWORD
        self._client: httpx.AsyncClient | None = None
        self._authenticated: bool = False

    @property
    def is_configured(self) -> bool:
        """Return True if qBittorrent connection details are set."""
        return bool(self.base_url)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
            )
            self._authenticated = False
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            self._authenticated = False

    async def _authenticate(self) -> None:
        """Authenticate with qBittorrent if not already logged in."""
        if self._authenticated:
            return
        client = await self._get_client()
        resp = await client.post(
            "/api/v2/auth/login",
            data={"username": self.username, "password": self.password},
        )
        resp.raise_for_status()
        if resp.text.strip().lower() == "ok.":
            self._authenticated = True
            logger.debug("Authenticated with qBittorrent")
        else:
            raise ConnectionError(f"qBittorrent authentication failed: {resp.text}")

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Execute request with automatic re-authentication if session expired (403)."""
        await self._authenticate()
        client = await self._get_client()
        resp = await client.request(method, path, **kwargs)
        if resp.status_code == 403:
            logger.debug("qBittorrent session expired (403); re-authenticating...")
            self._authenticated = False
            await self._authenticate()
            resp = await client.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp

    async def test_connection(self) -> dict[str, Any]:
        """Test the connection and return service info."""
        if not self.is_configured:
            return {"ok": False, "error": "qBittorrent URL not configured"}
        try:
            resp = await self._request("GET", "/api/v2/app/version")
            version = resp.text.strip()
            return {"ok": True, "version": version, "name": "qBittorrent"}
        except Exception as exc:
            logger.warning("qBittorrent connection test failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def get_torrents(
        self,
        filter_state: str = "all",
        category: str = "",
        hashes: str = "",
    ) -> list[dict[str, Any]]:
        """Return all torrents matching the filter criteria.

        Args:
            filter_state: Filter by state (all, downloading, seeding, etc.).
            category: Filter by category.
            hashes: Pipe-separated list of torrent hashes to filter.
        """
        params: dict[str, Any] = {"filter": filter_state}
        if category:
            params["category"] = category
        if hashes:
            params["hashes"] = hashes
        resp = await self._request("GET", "/api/v2/torrents/info", params=params)
        return resp.json()

    async def get_torrent_files(self, torrent_hash: str) -> list[dict[str, Any]]:
        """Return file list for a specific torrent.

        Args:
            torrent_hash: The torrent hash.
        """
        resp = await self._request(
            "GET", "/api/v2/torrents/files", params={"hash": torrent_hash}
        )
        return resp.json()

    async def get_torrent_properties(self, torrent_hash: str) -> dict[str, Any]:
        """Return properties for a specific torrent."""
        resp = await self._request(
            "GET", "/api/v2/torrents/properties", params={"hash": torrent_hash}
        )
        return resp.json()

    async def delete_torrent(
        self, torrent_hash: str, delete_files: bool = False
    ) -> bool:
        """Delete a torrent.

        Args:
            torrent_hash: The torrent hash.
            delete_files: Whether to also delete downloaded files.

        Returns:
            True if deletion was successful.
        """
        await self._request(
            "POST",
            "/api/v2/torrents/delete",
            data={
                "hashes": torrent_hash,
                "deleteFiles": str(delete_files).lower(),
            },
        )
        logger.info(
            "Deleted torrent %s (files=%s)", torrent_hash[:8], delete_files
        )
        return True

    async def pause_torrent(self, torrent_hash: str) -> bool:
        """Pause a torrent."""
        await self._request(
            "POST", "/api/v2/torrents/pause", data={"hashes": torrent_hash}
        )
        return True

    async def resume_torrent(self, torrent_hash: str) -> bool:
        """Resume a paused torrent."""
        await self._request(
            "POST", "/api/v2/torrents/resume", data={"hashes": torrent_hash}
        )
        return True

    async def find_torrent_by_file_path(self, file_path: str) -> dict[str, Any] | None:
        """Find the active/completed torrent associated with a file path."""
        import os
        base_name = os.path.basename(file_path)
        torrents = await self.get_torrents()

        # 1. Fast match by content_path or exact path
        for t in torrents:
            content_path = t.get("content_path", "")
            if content_path:
                if content_path == file_path or (len(content_path) >= 6 and (content_path in file_path or file_path.endswith(content_path))):
                    return t
            t_name = t.get("name", "")
            if t_name and (t_name == base_name or (len(t_name) >= 6 and t_name.lower() in file_path.lower())):
                return t

        # 2. Match by individual file names inside torrents
        for t in torrents:
            t_hash = t.get("hash")
            if not t_hash:
                continue
            try:
                files = await self.get_torrent_files(t_hash)
                for f in files:
                    f_name = f.get("name", "")
                    if base_name and (base_name == f_name or base_name == os.path.basename(f_name) or (len(base_name) >= 6 and base_name in f_name)):
                        return t
            except Exception:
                continue

        return None

    async def get_torrent_seeding_info(
        self, torrent_hash: str, min_ratio: float = 1.0, min_days: int = 90
    ) -> dict[str, Any]:
        """Check whether a torrent has met seeding ratio or time thresholds."""
        props = await self.get_torrent_properties(torrent_hash)
        torrents = await self.get_torrents(hashes=torrent_hash)
        torrent = torrents[0] if torrents else {}

        ratio = float(props.get("share_ratio", torrent.get("ratio", 0.0)))
        seeding_time_sec = int(props.get("seeding_time", torrent.get("seeding_time", 0)))
        seeding_time_days = seeding_time_sec / 86400.0

        meets_ratio = ratio >= min_ratio
        meets_time = seeding_time_days >= min_days
        can_delete = meets_ratio or meets_time

        return {
            "hash": torrent_hash,
            "name": torrent.get("name", props.get("name", "")),
            "ratio": ratio,
            "target_ratio": min_ratio,
            "seeding_time_seconds": seeding_time_sec,
            "seeding_time_days": seeding_time_days,
            "target_days": min_days,
            "meets_ratio": meets_ratio,
            "meets_time": meets_time,
            "can_delete": can_delete,
        }

    def parse_torrent(self, data: dict[str, Any]) -> TorrentInfo:
        """Parse a raw qBittorrent torrent dict into a TorrentInfo."""
        return TorrentInfo(
            hash=data.get("hash", ""),
            name=data.get("name", ""),
            save_path=data.get("save_path", ""),
            size=data.get("size", 0),
            ratio=data.get("ratio", 0.0),
            seeding_time=data.get("seeding_time", 0),
            state=data.get("state", ""),
            category=data.get("category", ""),
            tags=data.get("tags", ""),
            added_on=data.get("added_on", 0),
            content_path=data.get("content_path", ""),
        )
