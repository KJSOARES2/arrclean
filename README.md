# ArrClean — Automated Media Deduplication & Lifecycle Manager

<p align="center">
  <img src="frontend/public/favicon.svg" width="96" height="96" alt="ArrClean Logo" />
</p>

<p align="center">
  <strong>Production-ready, Dockerized automated media deduplication, quality evaluation, and seeding retention manager for Plex, Radarr, Sonarr, Overseerr, Prowlarr, SABnzbd, and qBittorrent.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?logo=python" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react" alt="React 18" />
  <img src="https://img.shields.io/badge/TailwindCSS-3.4-38B2AC?logo=tailwind-css" alt="Tailwind" />
  <img src="https://img.shields.io/badge/Docker-Multi--stage-2496ED?logo=docker" alt="Docker" />
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License" />
</p>

---

## 1. Overview & Objective

Large media libraries frequently accumulate duplicate copies of movies and TV episodes due to manual upgrades, multi-source grabs, or failed cleanup tasks across the *arr stack.

**ArrClean** scans your media library, performs technical inspection of every audio/video stream using `ffprobe` and `mediainfo`, calculates custom format scores from Radarr and Sonarr, designates the single highest-quality copy to retain, and safely removes inferior duplicates while **strictly honoring torrent seeding rules** and preventing redundant re-downloads.

---

## 2. Key Architecture & Features

### 🎯 Intelligent Quality Scoring Hierarchy
When two or more files exist for the same movie (TMDB) or episode (TVDB), ArrClean evaluates them using a deterministic hierarchy:
1. **Primary Score:** Radarr/Sonarr **Custom Format (CF) Score** and Quality Profile Rank (50% primary weight).
2. **Resolution:** `2160p (4K)` > `1080p` > `720p` > `SD`.
3. **Dynamic Range:** `Dolby Vision + HDR10+` > `Dolby Vision` > `HDR10+` > `HDR10` > `SDR`.
4. **Source:** `Remux` > `BluRay` > `WEB-DL` > `WEBRip` > `HDTV`.
5. **Audio Codec:** `TrueHD Atmos / DTS:X` > `DTS-HD MA` > `EAC3 Atmos` > `AC3 / AAC`.
6. **Video Codec & Bitrate:** `AV1 / HEVC (H.265)` preferred over `H.264` at equivalent tiers; higher bitrate serves as tiebreaker.
7. **Edition Consolidation:** Configurable toggle to either preserve distinct cuts (e.g., *Director's Cut* vs. *Theatrical*) or consolidate them into the highest-rated edition.

### 🛡️ qBittorrent Seeding & Hardlink Safeguards
Media servers often use hardlinks (`os.stat().st_nlink > 1`) between qBittorrent download folders and Plex/media folders.
* **Retention Criteria:** A duplicate backed by a qBittorrent torrent is only fully deleted if:
  * `ratio >= 1.0` **OR**
  * `seeding_time >= 90 days` (configurable).
* **Seed-Lock State:** If criteria are not yet met:
  * The library-side hardlink is safely removed (`st_nlink` decrements from 2 to 1). Plex stops showing duplicate entries.
  * The torrent-side seed file remains **completely intact** in qBittorrent to maintain your private tracker ratio.
  * The torrent enters the **"Pending Seed Completion"** database queue.
  * A background monitor watches progress and automatically purges the torrent and disk data the moment ratio or duration is satisfied.

### 🚫 Queue Interception Worker
Periodically scans active download queues in Radarr, Sonarr, SABnzbd, and qBittorrent. If an item being downloaded is inferior or equal to an existing file already on disk, ArrClean automatically cancels the download, blocklists the release, and cleans the queue.

### 📊 Modern Dark-Mode Web Dashboard
* **Executive Telemetry:** Lifetime GB/TB space reclaimed, pending space in seed-locks, and a 30-day interactive area chart.
* **Breakdown Visualizations:** Duplicates categorized by resolution (4K vs 1080p), dynamic range (HDR vs SDR), and acquisition source (Usenet vs Torrents).
* **Duplicates Review Queue:** Side-by-side cards comparing winners vs losers with swap, approve, ignore, and force-delete options.
* **Seeding Watchlist:** Real-time ratio and days progress bars with estimated unlock dates.
* **Live WebSocket Console:** Real-time streaming log terminal with level filters.
* **Notification Webhooks:** Formatted alerts to Discord, Notifiarr, and Gotify.

---

## 3. Quick Start Deployment

### Using Docker Compose (Recommended)

1. Clone or download the repository:
   ```bash
   git clone https://github.com/your-username/arrclean.git
   cd arrclean
   ```

2. Copy the environment template:
   ```bash
   cp .env.example .env
   ```

3. Configure your paths in `docker-compose.yml`:
   ```yaml
   services:
     arrclean:
       build: .
       container_name: arrclean
       ports:
         - "9494:9494"
       environment:
         - PUID=1000
         - PGID=1000
         - TZ=America/Chicago
       env_file:
         - .env
       volumes:
         - ./data:/app/data
         - /path/to/media:/media
         - /path/to/downloads:/downloads
       restart: unless-stopped
   ```

4. Start the container:
   ```bash
   docker compose up -d --build
   ```

5. Open your browser and navigate to:
   ```
   http://localhost:9494
   ```

> [!NOTE]
> **Dry-Run Mode** is enabled by default on first boot (`ARRCLEAN_DRY_RUN=true`). Scans will detect duplicates and show you planned actions in the UI without deleting any files until you toggle Dry-Run off in Settings.

---

## 4. Configuration Reference

All settings can be configured via environment variables or modified directly in the **Settings & Safety** web UI:

| Variable | Default | Description |
|---|---|---|
| `ARRCLEAN_DRY_RUN` | `true` | When true, no files or torrents are deleted |
| `ARRCLEAN_DATABASE_URL` | `sqlite+aiosqlite:///./data/arrclean.db` | SQLite or PostgreSQL connection string |
| `ARRCLEAN_SCAN_CRON` | `0 3 * * *` | Cron schedule for library deduplication scan (3 AM daily) |
| `ARRCLEAN_SEED_MONITOR_INTERVAL_MINUTES` | `30` | Interval between qBittorrent seed checks |
| `ARRCLEAN_QUEUE_CHECK_INTERVAL_MINUTES` | `15` | Interval between download queue checks |
| `ARRCLEAN_MIN_SEED_RATIO` | `1.0` | Minimum share ratio before torrent purge |
| `ARRCLEAN_MIN_SEED_DAYS` | `90` | Minimum seeding days before torrent purge |
| `ARRCLEAN_EDITION_CONSOLIDATE` | `true` | Consolidate multi-editions into single highest quality |
| `ARRCLEAN_PLEX_URL` | `""` | Plex Media Server URL |
| `ARRCLEAN_PLEX_TOKEN` | `""` | Plex authentication token |
| `ARRCLEAN_RADARR_URL` | `""` | Radarr v3/v4/v5 API base URL |
| `ARRCLEAN_RADARR_APIKEY` | `""` | Radarr API key |
| `ARRCLEAN_SONARR_URL` | `""` | Sonarr v3/v4 API base URL |
| `ARRCLEAN_SONARR_APIKEY` | `""` | Sonarr API key |
| `ARRCLEAN_QBITTORRENT_URL` | `""` | qBittorrent Web UI URL |
| `ARRCLEAN_QBITTORRENT_USERNAME` | `""` | qBittorrent username |
| `ARRCLEAN_QBITTORRENT_PASSWORD` | `""` | qBittorrent password |
| `ARRCLEAN_SABNZBD_URL` | `""` | SABnzbd URL |
| `ARRCLEAN_SABNZBD_APIKEY` | `""` | SABnzbd API key |
| `ARRCLEAN_OVERSEERR_URL` | `""` | Overseerr / Jellyseerr URL |
| `ARRCLEAN_OVERSEERR_APIKEY` | `""` | Overseerr / Jellyseerr API key |
| `ARRCLEAN_PROWLARR_URL` | `""` | Prowlarr URL |
| `ARRCLEAN_PROWLARR_APIKEY` | `""` | Prowlarr API key |
| `ARRCLEAN_DISCORD_WEBHOOK_URL` | `""` | Discord webhook URL for run notifications |

---

## 5. REST API Overview

ArrClean exposes a complete OpenAPI-documented backend:

* `GET /api/v1/dashboard/stats` — Aggregate metrics and active scan status
* `GET /api/v1/dashboard/history?days=30` — Daily space reclaimed history
* `GET /api/v1/dashboard/breakdown` — Resolution, HDR, and source breakdown charts
* `GET /api/v1/duplicates` — Paginated list of duplicate pairs with filtering
* `POST /api/v1/duplicates/{id}/approve` — Approve winner and schedule loser cleanup
* `POST /api/v1/duplicates/{id}/swap` — Invert winner and loser designations
* `POST /api/v1/duplicates/{id}/force-delete` — Force delete duplicate bypassing seeding rules
* `GET /api/v1/seed-watch` — List active seed-locked torrents and ratio progress
* `POST /api/v1/settings/scan/trigger` — Trigger immediate library scan
* `POST /api/v1/connections/test` — Test credentials for any connected service
* `WS /api/v1/ws/logs` — Real-time WebSocket log stream

Interactive Swagger API documentation is available at `http://localhost:9494/docs`.

---

## 6. Running Tests

ArrClean includes automated pytest unit tests covering scoring algorithms, string parsers, hardlink utilities, scanner logic, and REST endpoints:

```bash
# In the virtual environment:
pytest backend/tests -v
```

All 33 test suites run in under a second and execute asynchronously against in-memory SQLite fixtures.

---

## 7. License

MIT License. See [LICENSE](LICENSE) for details.
