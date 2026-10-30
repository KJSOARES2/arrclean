"""Tests for duplicate detection scanner logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.engine.dedup_scanner import DedupScanner
from app.engine.quality_scorer import QualityScorer
from app.models.duplicate import DuplicatePair, DuplicateRecord
from app.models.job_history import JobStatus, ScanJob
from app.services import ServiceManager


@pytest.mark.asyncio
async def test_scanner_creates_job_record(db_session: AsyncSession) -> None:
    session_factory = MagicMock()
    session_factory.return_value.__aenter__.return_value = db_session
    session_factory.return_value.__aexit__.return_value = None

    services = MagicMock(spec=ServiceManager)
    services.plex = MagicMock()
    services.plex.is_configured = False
    services.radarr = MagicMock()
    services.radarr.is_configured = False
    services.sonarr = MagicMock()
    services.sonarr.is_configured = False
    services.qbittorrent = MagicMock()
    services.qbittorrent.is_configured = False
    services.notifications = MagicMock()
    services.notifications.has_any_configured = False

    scanner = DedupScanner(
        service_manager=services,
        session_factory=session_factory,
        settings=Settings(DRY_RUN=True),
    )

    result = await scanner.run_full_scan()
    assert result["status"] == "completed"

    # Verify ScanJob in DB
    stmt = select(ScanJob)
    jobs = list((await db_session.execute(stmt)).scalars().all())
    assert len(jobs) == 1
    assert jobs[0].status == JobStatus.COMPLETED


@pytest.mark.asyncio
async def test_scanner_evaluates_candidates_and_selects_winner() -> None:
    services = MagicMock()
    services.qbittorrent.is_configured = False

    scanner = DedupScanner(service_manager=services, settings=Settings(DRY_RUN=True))

    candidates = [
        {
            "record": {
                "media_type": "movie",
                "title": "Inception (2010)",
                "file_path": "/movies/Inception.1080p.mkv",
                "file_size_bytes": 10_000_000_000,
            },
            "score": 350.0,
        },
        {
            "record": {
                "media_type": "movie",
                "title": "Inception (2010)",
                "file_path": "/movies/Inception.2160p.mkv",
                "file_size_bytes": 35_000_000_000,
            },
            "score": 850.0,
        },
    ]

    pairs = scanner._create_pairs_from_candidates(candidates)
    assert len(pairs) == 1
    pair = pairs[0]

    # Winner should be 2160p with score 850.0
    assert pair["winner"]["file_path"] == "/movies/Inception.2160p.mkv"
    # Loser should be 1080p
    assert pair["loser"]["file_path"] == "/movies/Inception.1080p.mkv"
    assert pair["space_saved"] == 10_000_000_000
