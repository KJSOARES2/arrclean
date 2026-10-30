"""External service integrations for ArrClean."""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings, get_settings
from app.services.base import (
    BaseServiceClient,
    ServiceAuthenticationError,
    ServiceConnectionError,
    ServiceError,
    ServiceNotFoundError,
    ServiceUnavailableError,
    ServiceValidationError,
)
from app.services.notifications import NotificationService
from app.services.overseerr import OverseerrClient
from app.services.plex import PlexClient
from app.services.prowlarr import ProwlarrClient
from app.services.qbittorrent import QBittorrentClient
from app.services.radarr import RadarrClient
from app.services.sabnzbd import SABnzbdClient
from app.services.sonarr import SonarrClient

logger = logging.getLogger(__name__)


class ServiceManager:
    """Central manager for all external service integrations.

    Maintains active instances of each client, provides unified connection
    testing, and handles safe cleanup during application shutdown.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.plex = PlexClient(url=self.settings.PLEX_URL, token=self.settings.PLEX_TOKEN)
        self.radarr = RadarrClient(url=self.settings.RADARR_URL, apikey=self.settings.RADARR_APIKEY)
        self.sonarr = SonarrClient(url=self.settings.SONARR_URL, apikey=self.settings.SONARR_APIKEY)
        self.qbittorrent = QBittorrentClient(
            url=self.settings.QBITTORRENT_URL,
            username=self.settings.QBITTORRENT_USERNAME,
            password=self.settings.QBITTORRENT_PASSWORD,
        )
        self.sabnzbd = SABnzbdClient(url=self.settings.SABNZBD_URL, apikey=self.settings.SABNZBD_APIKEY)
        self.overseerr = OverseerrClient(url=self.settings.OVERSEERR_URL, apikey=self.settings.OVERSEERR_APIKEY)
        self.prowlarr = ProwlarrClient(url=self.settings.PROWLARR_URL, apikey=self.settings.PROWLARR_APIKEY)
        self.notifications = NotificationService()

    def reload(self, settings: Settings | None = None) -> None:
        """Update clients with refreshed settings."""
        self.settings = settings or get_settings()
        self.plex = PlexClient(url=self.settings.PLEX_URL, token=self.settings.PLEX_TOKEN)
        self.radarr = RadarrClient(url=self.settings.RADARR_URL, apikey=self.settings.RADARR_APIKEY)
        self.sonarr = SonarrClient(url=self.settings.SONARR_URL, apikey=self.settings.SONARR_APIKEY)
        self.qbittorrent = QBittorrentClient(
            url=self.settings.QBITTORRENT_URL,
            username=self.settings.QBITTORRENT_USERNAME,
            password=self.settings.QBITTORRENT_PASSWORD,
        )
        self.sabnzbd = SABnzbdClient(url=self.settings.SABNZBD_URL, apikey=self.settings.SABNZBD_APIKEY)
        self.overseerr = OverseerrClient(url=self.settings.OVERSEERR_URL, apikey=self.settings.OVERSEERR_APIKEY)
        self.prowlarr = ProwlarrClient(url=self.settings.PROWLARR_URL, apikey=self.settings.PROWLARR_APIKEY)
        self.notifications = NotificationService()

    async def test_all_connections(self) -> dict[str, dict[str, Any]]:
        """Test connections to all configured services concurrently."""
        results: dict[str, dict[str, Any]] = {}

        services: list[tuple[str, Any]] = [
            ("plex", self.plex),
            ("radarr", self.radarr),
            ("sonarr", self.sonarr),
            ("qbittorrent", self.qbittorrent),
            ("sabnzbd", self.sabnzbd),
            ("overseerr", self.overseerr),
            ("prowlarr", self.prowlarr),
        ]

        for name, client in services:
            if not getattr(client, "is_configured", False):
                results[name] = {
                    "configured": False,
                    "connected": False,
                    "message": "Not configured",
                }
                continue

            try:
                res = await client.test_connection()
                results[name] = {
                    "configured": True,
                    "connected": res.get("status") in ("ok", "success") or res.get("connected", False) or "version" in res,
                    "details": res,
                }
            except Exception as e:
                logger.warning("Connection test failed for %s: %s", name, e)
                results[name] = {
                    "configured": True,
                    "connected": False,
                    "error": str(e),
                }

        results["notifications"] = {
            "configured": self.notifications.has_any_configured,
            "connected": self.notifications.has_any_configured,
            "channels": {
                "discord": bool(self.settings.DISCORD_WEBHOOK_URL),
                "notifiarr": bool(self.settings.NOTIFIARR_APIKEY),
                "gotify": bool(self.settings.GOTIFY_URL and self.settings.GOTIFY_TOKEN),
            },
        }

        return results

    async def close_all(self) -> None:
        """Close all open HTTP connections."""
        clients = [
            self.plex,
            self.radarr,
            self.sonarr,
            self.qbittorrent,
            self.sabnzbd,
            self.overseerr,
            self.prowlarr,
            self.notifications,
        ]
        for client in clients:
            try:
                await client.close()
            except Exception as e:
                logger.debug("Error closing client %s: %s", client, e)


_service_manager: ServiceManager | None = None


def get_service_manager() -> ServiceManager:
    """Return the singleton ServiceManager."""
    global _service_manager
    if _service_manager is None:
        _service_manager = ServiceManager()
    return _service_manager


__all__ = [
    "BaseServiceClient",
    "ServiceError",
    "ServiceConnectionError",
    "ServiceAuthenticationError",
    "ServiceNotFoundError",
    "ServiceValidationError",
    "ServiceUnavailableError",
    "PlexClient",
    "RadarrClient",
    "SonarrClient",
    "QBittorrentClient",
    "SABnzbdClient",
    "OverseerrClient",
    "ProwlarrClient",
    "NotificationService",
    "ServiceManager",
    "get_service_manager",
]
