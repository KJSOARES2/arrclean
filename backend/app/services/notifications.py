"""Notification service supporting Discord, Notifiarr, and Gotify.

Sends formatted notifications about ArrClean events such as scan
completions, duplicate resolutions, and error alerts.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class NotificationService:
    """Sends notifications to configured services (Discord, Notifiarr, Gotify)."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @property
    def has_any_configured(self) -> bool:
        """Return True if at least one notification service is configured."""
        return bool(
            self.settings.DISCORD_WEBHOOK_URL
            or self.settings.NOTIFIARR_APIKEY
            or (self.settings.GOTIFY_URL and self.settings.GOTIFY_TOKEN)
        )

    async def send(
        self,
        title: str,
        message: str,
        *,
        color: int = 0x3498DB,
        fields: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Send a notification to all configured services.

        Args:
            title: Notification title.
            message: Notification body.
            color: Embed color (Discord) as an integer.
            fields: Optional list of ``{"name": ..., "value": ...}`` field dicts.

        Returns:
            Dict mapping service name to success/error status.
        """
        results: dict[str, Any] = {}

        if self.settings.DISCORD_WEBHOOK_URL:
            results["discord"] = await self._send_discord(title, message, color, fields)

        if self.settings.NOTIFIARR_APIKEY:
            results["notifiarr"] = await self._send_notifiarr(title, message)

        if self.settings.GOTIFY_URL and self.settings.GOTIFY_TOKEN:
            results["gotify"] = await self._send_gotify(title, message)

        if not results:
            logger.debug("No notification services configured; skipping notification.")
            results["status"] = "no_services_configured"

        return results

    async def _send_discord(
        self,
        title: str,
        message: str,
        color: int,
        fields: list[dict[str, str]] | None,
    ) -> dict[str, Any]:
        """Send a Discord webhook notification."""
        try:
            client = await self._get_client()
            embed: dict[str, Any] = {
                "title": f"🧹 ArrClean — {title}",
                "description": message,
                "color": color,
            }
            if fields:
                embed["fields"] = [
                    {"name": f["name"], "value": f["value"], "inline": True}
                    for f in fields
                ]
            payload = {"embeds": [embed]}
            resp = await client.post(self.settings.DISCORD_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
            return {"ok": True}
        except Exception as exc:
            logger.warning("Discord notification failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def _send_notifiarr(self, title: str, message: str) -> dict[str, Any]:
        """Send a Notifiarr notification."""
        try:
            client = await self._get_client()
            payload = {
                "notification": {
                    "name": title,
                    "message": message,
                }
            }
            resp = await client.post(
                "https://notifiarr.com/api/v1/notification/passthrough",
                json=payload,
                headers={"x-api-key": self.settings.NOTIFIARR_APIKEY},
            )
            resp.raise_for_status()
            return {"ok": True}
        except Exception as exc:
            logger.warning("Notifiarr notification failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def _send_gotify(self, title: str, message: str) -> dict[str, Any]:
        """Send a Gotify notification."""
        try:
            client = await self._get_client()
            url = f"{self.settings.GOTIFY_URL.rstrip('/')}/message"
            payload = {
                "title": f"ArrClean — {title}",
                "message": message,
                "priority": 5,
            }
            resp = await client.post(
                url,
                json=payload,
                headers={"X-Gotify-Key": self.settings.GOTIFY_TOKEN},
            )
            resp.raise_for_status()
            return {"ok": True}
        except Exception as exc:
            logger.warning("Gotify notification failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def notify_scan_complete(
        self,
        duplicates_found: int,
        duplicates_resolved: int = 0,
        space_reclaimed_bytes: int = 0,
        space_reclaimable: int | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Send a scan completion notification.

        Args:
            duplicates_found: Number of duplicate pairs found.
            duplicates_resolved: Number of duplicate pairs resolved.
            space_reclaimed_bytes: Total space savings in bytes.
            space_reclaimable: Alias for space_reclaimed_bytes.
            error: Optional error message if scan had failures.
        """
        bytes_val = space_reclaimable if space_reclaimable is not None else space_reclaimed_bytes
        space_gb = bytes_val / (1024**3)
        msg = f"Found **{duplicates_found}** duplicate pairs.\nPotential space savings: **{space_gb:.1f} GB**"
        if error:
            msg += f"\n⚠️ Error: {error}"

        fields = [
            {"name": "Duplicates Found", "value": str(duplicates_found)},
            {"name": "Potential Space", "value": f"{space_gb:.1f} GB"},
        ]
        if duplicates_resolved:
            fields.append({"name": "Resolved", "value": str(duplicates_resolved)})

        return await self.send(
            "Scan Complete",
            msg,
            color=0xE74C3C if error else 0x2ECC71,
            fields=fields,
        )

    async def notify_cleanup_complete(
        self,
        files_removed: int,
        space_reclaimed: int,
    ) -> dict[str, Any]:
        """Send a cleanup completion notification."""
        space_gb = space_reclaimed / (1024**3)
        return await self.send(
            "Cleanup Complete",
            f"Removed **{files_removed}** duplicate files.\n"
            f"Space reclaimed: **{space_gb:.1f} GB**",
            color=0xE74C3C,
            fields=[
                {"name": "Files Removed", "value": str(files_removed)},
                {"name": "Reclaimed", "value": f"{space_gb:.1f} GB"},
            ],
        )

    async def notify_error(self, error_message: str) -> dict[str, Any]:
        """Send an error notification."""
        return await self.send(
            "Error",
            f"⚠️ {error_message}",
            color=0xE74C3C,
        )
