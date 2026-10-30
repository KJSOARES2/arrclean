"""Application configuration using pydantic-settings.

All settings are loaded from environment variables with the ARRCLEAN_ prefix.
For example, ARRCLEAN_DATABASE_URL, ARRCLEAN_DRY_RUN, etc.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """ArrClean application settings.

    All values can be overridden via environment variables prefixed with
    ``ARRCLEAN_``.  For example ``ARRCLEAN_DRY_RUN=false``.
    """

    model_config = SettingsConfigDict(
        env_prefix="ARRCLEAN_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Core ────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./data/arrclean.db",
        description="Database connection URL. Supports SQLite and PostgreSQL.",
    )
    LOG_LEVEL: str = Field(default="INFO", description="Logging level.")
    DRY_RUN: bool = Field(
        default=True,
        description="When True no destructive actions are taken. Enabled on first boot for safety.",
    )

    # ── Scheduling ──────────────────────────────────────────────────────
    SCAN_CRON: str = Field(
        default="0 3 * * *",
        description="Cron expression for the full duplicate scan (default 3 AM daily).",
    )
    SEED_MONITOR_INTERVAL_MINUTES: int = Field(
        default=30,
        description="Interval in minutes between seed-lock monitor runs.",
    )
    QUEUE_CHECK_INTERVAL_MINUTES: int = Field(
        default=15,
        description="Interval in minutes between download-queue interception checks.",
    )

    # ── Plex ────────────────────────────────────────────────────────────
    PLEX_URL: str = Field(default="", description="Plex Media Server URL.")
    PLEX_TOKEN: str = Field(default="", description="Plex authentication token.")

    # ── Radarr ──────────────────────────────────────────────────────────
    RADARR_URL: str = Field(default="", description="Radarr API base URL.")
    RADARR_APIKEY: str = Field(default="", description="Radarr API key.")

    # ── Sonarr ──────────────────────────────────────────────────────────
    SONARR_URL: str = Field(default="", description="Sonarr API base URL.")
    SONARR_APIKEY: str = Field(default="", description="Sonarr API key.")

    # ── qBittorrent ─────────────────────────────────────────────────────
    QBITTORRENT_URL: str = Field(default="", description="qBittorrent Web UI URL.")
    QBITTORRENT_USERNAME: str = Field(default="", description="qBittorrent username.")
    QBITTORRENT_PASSWORD: str = Field(default="", description="qBittorrent password.")

    # ── SABnzbd ─────────────────────────────────────────────────────────
    SABNZBD_URL: str = Field(default="", description="SABnzbd URL.")
    SABNZBD_APIKEY: str = Field(default="", description="SABnzbd API key.")

    # ── Overseerr / Jellyseerr ──────────────────────────────────────────
    OVERSEERR_URL: str = Field(default="", description="Overseerr/Jellyseerr URL.")
    OVERSEERR_APIKEY: str = Field(default="", description="Overseerr/Jellyseerr API key.")

    # ── Prowlarr ────────────────────────────────────────────────────────
    PROWLARR_URL: str = Field(default="", description="Prowlarr URL.")
    PROWLARR_APIKEY: str = Field(default="", description="Prowlarr API key.")

    # ── Notifications ───────────────────────────────────────────────────
    DISCORD_WEBHOOK_URL: str = Field(default="", description="Discord webhook URL for notifications.")
    NOTIFIARR_APIKEY: str = Field(default="", description="Notifiarr API key.")
    GOTIFY_URL: str = Field(default="", description="Gotify server URL.")
    GOTIFY_TOKEN: str = Field(default="", description="Gotify application token.")

    # ── Seeding thresholds ──────────────────────────────────────────────
    MIN_SEED_RATIO: float = Field(
        default=1.0,
        description="Minimum seed ratio before a torrent can be purged.",
    )
    MIN_SEED_DAYS: int = Field(
        default=90,
        description="Minimum days seeding before a torrent can be purged.",
    )

    # ── Feature flags ───────────────────────────────────────────────────
    EDITION_CONSOLIDATE: bool = Field(
        default=True,
        description="Consolidate editions (e.g. Theatrical vs Director's Cut) during dedup.",
    )

    # ── Quality weight overrides ────────────────────────────────────────
    WEIGHT_RESOLUTION: float = Field(default=1.0, description="Weight for resolution scoring.")
    WEIGHT_HDR: float = Field(default=1.0, description="Weight for HDR format scoring.")
    WEIGHT_SOURCE: float = Field(default=1.0, description="Weight for source type scoring.")
    WEIGHT_AUDIO: float = Field(default=1.0, description="Weight for audio codec scoring.")
    WEIGHT_CODEC: float = Field(default=1.0, description="Weight for video codec scoring.")


_settings_instance: Settings | None = None


def get_settings() -> Settings:
    """Return a cached instance of application settings."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


def reload_settings(overrides: dict[str, Any] | None = None) -> Settings:
    """Reload settings, optionally merging database overrides."""
    global _settings_instance
    base = Settings()
    if overrides:
        for k, v in overrides.items():
            if hasattr(base, k) and v is not None:
                setattr(base, k, v)
    _settings_instance = base
    return _settings_instance
