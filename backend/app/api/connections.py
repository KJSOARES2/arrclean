"""Endpoints for testing and querying external service integrations."""

from __future__ import annotations

import ipaddress
import logging
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings
from app.services import (
    NotificationService,
    OverseerrClient,
    PlexClient,
    ProwlarrClient,
    QBittorrentClient,
    RadarrClient,
    SABnzbdClient,
    SonarrClient,
    get_service_manager,
)

logger = logging.getLogger("arrclean.api.connections")

router = APIRouter(prefix="/connections", tags=["connections"])


def _clean_credential(val: str | None, fallback: str) -> str:
    """Return stripped credential or fallback if value is empty or masked."""
    if not val:
        return fallback or ""
    v = val.strip()
    if not v or "•" in v or v == "••••••••":
        return fallback or ""
    return v


def _is_safe_service_url(url_str: str | None) -> tuple[bool, str]:
    """Validate that the provided service URL is safe and not targeting cloud metadata."""
    if not url_str:
        return True, ""
    try:
        parsed = urlparse(url_str)
        if parsed.scheme not in ("http", "https"):
            return False, "Only HTTP and HTTPS URLs are permitted"
        hostname = parsed.hostname
        if not hostname:
            return False, "Invalid URL: missing hostname"
        if hostname.lower() in ("metadata.google.internal", "instance-data", "169.254.169.254"):
            return False, "Cloud metadata endpoints are forbidden"
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_link_local:
                return False, "Link-local / metadata addresses are forbidden"
        except ValueError:
            pass
        return True, ""
    except Exception as e:
        return False, f"Invalid URL: {e}"


class ConnectionTestRequest(BaseModel):
    service: str
    url: str | None = None
    token: str | None = None
    apikey: str | None = None
    username: str | None = None
    password: str | None = None


class NotificationTestRequest(BaseModel):
    channel: str  # "discord", "notifiarr", "gotify", or "all"


@router.get("/status")
async def get_connections_status() -> dict[str, Any]:
    """Test and return the real-time health of all configured services."""
    sm = get_service_manager()
    return await sm.test_all_connections()


@router.post("/test")
async def test_single_connection(req: ConnectionTestRequest) -> dict[str, Any]:
    """Test connection credentials for a specific external service."""
    service = req.service.lower()
    details: dict[str, Any] = {}
    success = False
    error: str | None = None

    # SSRF verification on user-supplied URL
    is_safe, url_err = _is_safe_service_url(req.url)
    if not is_safe:
        return {
            "service": service,
            "success": False,
            "details": {},
            "error": f"Security validation error: {url_err}",
        }

    settings = get_settings()

    try:
        if service == "plex":
            token = _clean_credential(req.token, settings.PLEX_TOKEN)
            url = (req.url or settings.PLEX_URL or "").strip()
            client = PlexClient(url=url, token=token)
            details = await client.test_connection()
            success = details.get("connected", False) or "server_name" in details or "version" in details
            await client.close()

        elif service == "radarr":
            apikey = _clean_credential(req.apikey or req.token, settings.RADARR_APIKEY)
            url = (req.url or settings.RADARR_URL or "").strip()
            client = RadarrClient(url=url, apikey=apikey)
            details = await client.test_connection()
            success = details.get("ok", False) or "version" in details
            await client.close()

        elif service == "sonarr":
            apikey = _clean_credential(req.apikey or req.token, settings.SONARR_APIKEY)
            url = (req.url or settings.SONARR_URL or "").strip()
            client = SonarrClient(url=url, apikey=apikey)
            details = await client.test_connection()
            success = details.get("ok", False) or "version" in details
            await client.close()

        elif service == "qbittorrent":
            username = req.username if req.username is not None and req.username != "" else settings.QBITTORRENT_USERNAME
            password = _clean_credential(req.password, settings.QBITTORRENT_PASSWORD)
            url = (req.url or settings.QBITTORRENT_URL or "").strip()
            client = QBittorrentClient(
                url=url, username=username or "", password=password or ""
            )
            details = await client.test_connection()
            success = details.get("connected", False) or "version" in details
            await client.close()

        elif service == "sabnzbd":
            apikey = _clean_credential(req.apikey or req.token, settings.SABNZBD_APIKEY)
            url = (req.url or settings.SABNZBD_URL or "").strip()
            client = SABnzbdClient(url=url, apikey=apikey)
            details = await client.test_connection()
            success = details.get("ok", False) or "version" in details
            await client.close()

        elif service == "overseerr":
            apikey = _clean_credential(req.apikey or req.token, settings.OVERSEERR_APIKEY)
            url = (req.url or settings.OVERSEERR_URL or "").strip()
            client = OverseerrClient(url=url, apikey=apikey)
            details = await client.test_connection()
            success = details.get("ok", False) or "version" in details
            await client.close()

        elif service == "prowlarr":
            apikey = _clean_credential(req.apikey or req.token, settings.PROWLARR_APIKEY)
            url = (req.url or settings.PROWLARR_URL or "").strip()
            client = ProwlarrClient(url=url, apikey=apikey)
            details = await client.test_connection()
            success = details.get("ok", False) or "version" in details
            await client.close()

        else:
            error = f"Unsupported service: {service}"

    except Exception as e:
        logger.warning("Connection test failed for %s: %s", service, e)
        error = str(e)
        success = False

    if not success and not error:
        error = details.get("error") or "Connection test failed. Check URL and credentials."

    return {
        "service": service,
        "success": success,
        "details": details,
        "error": error,
    }


@router.post("/test-notification")
async def test_notification(req: NotificationTestRequest) -> dict[str, Any]:
    """Dispatch a test notification to verified alert channels."""
    notifier = get_service_manager().notifications
    channel = req.channel.lower()
    res: dict[str, Any] = {}

    test_title = "ArrClean Test Notification"
    test_msg = "ArrClean connection test successful. Quality deduplication and seeding rules active."

    if channel in ("discord", "all"):
        res["discord"] = await notifier._send_discord(test_title, test_msg)
    if channel in ("notifiarr", "all"):
        res["notifiarr"] = await notifier._send_notifiarr(test_title, test_msg)
    if channel in ("gotify", "all"):
        res["gotify"] = await notifier._send_gotify(test_title, test_msg)

    return {"status": "dispatched", "results": res}
