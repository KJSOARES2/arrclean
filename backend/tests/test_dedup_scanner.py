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


@pytest.mark.asyncio
async def test_prune_ghost_and_duplicate_pairs(db_session: AsyncSession) -> None:
    from app.engine.dedup_scanner import prune_ghost_and_duplicate_pairs
    from app.models.duplicate import ActionTaken, DuplicatePairStatus

    # Create records
    w1 = DuplicateRecord(media_type="movie", title="Movie A", file_path="/movies/a_4k.mkv", file_size_bytes=30_000_000_000)
    l1 = DuplicateRecord(media_type="movie", title="Movie A", file_path="/movies/a_1080p.mkv", file_size_bytes=10_000_000_000)
    w2 = DuplicateRecord(media_type="movie", title="Movie A", file_path="/movies/a_4k.mkv", file_size_bytes=30_000_000_000)
    l2 = DuplicateRecord(media_type="movie", title="Movie A", file_path="/movies/a_1080p.mkv", file_size_bytes=10_000_000_000)
    w3 = DuplicateRecord(media_type="movie", title="Movie A", file_path="/movies/a_4k.mkv", file_size_bytes=30_000_000_000)
    l3 = DuplicateRecord(media_type="movie", title="Movie A", file_path="/movies/a_1080p.mkv", file_size_bytes=10_000_000_000)
    db_session.add_all([w1, l1, w2, l2, w3, l3])
    await db_session.flush()

    # Pair 1: First COMPLETED run
    p1 = DuplicatePair(
        media_type="movie",
        title="Movie A",
        winner_record_id=w1.id,
        loser_record_id=l1.id,
        status=DuplicatePairStatus.COMPLETED,
        action_taken=ActionTaken.DELETED,
        space_saved_bytes=10_000_000_000,
    )
    # Pair 2: Redundant COMPLETED run for same loser file
    p2 = DuplicatePair(
        media_type="movie",
        title="Movie A",
        winner_record_id=w2.id,
        loser_record_id=l2.id,
        status=DuplicatePairStatus.COMPLETED,
        action_taken=ActionTaken.DELETED,
        space_saved_bytes=10_000_000_000,
    )
    # Pair 3: Ghost PENDING_REVIEW run for same loser file
    p3 = DuplicatePair(
        media_type="movie",
        title="Movie A",
        winner_record_id=w3.id,
        loser_record_id=l3.id,
        status=DuplicatePairStatus.PENDING_REVIEW,
        action_taken=ActionTaken.NONE,
        space_saved_bytes=10_000_000_000,
    )
    db_session.add_all([p1, p2, p3])
    await db_session.commit()

    # Run pruning
    stats = await prune_ghost_and_duplicate_pairs(db_session)
    assert stats["pruned_redundant_completed"] == 1
    assert stats["pruned_ghost_pending"] == 1

    # Verify only p1 remains
    remaining = list((await db_session.execute(select(DuplicatePair))).scalars().all())
    assert len(remaining) == 1
    assert remaining[0].id == p1.id


@pytest.mark.asyncio
async def test_completed_pair_blocks_resurrection_in_scan(db_session: AsyncSession) -> None:
    from app.models.duplicate import ActionTaken, DuplicatePairStatus

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

    # Insert an existing COMPLETED pair
    w = DuplicateRecord(media_type="movie", title="Movie B", file_path="/movies/b_4k.mkv", file_size_bytes=20_000_000_000)
    l = DuplicateRecord(media_type="movie", title="Movie B", file_path="/movies/b_1080p.mkv", file_size_bytes=5_000_000_000)
    db_session.add_all([w, l])
    await db_session.flush()

    p = DuplicatePair(
        media_type="movie",
        title="Movie B",
        winner_record_id=w.id,
        loser_record_id=l.id,
        status=DuplicatePairStatus.COMPLETED,
        action_taken=ActionTaken.DELETED,
        space_saved_bytes=5_000_000_000,
    )
    db_session.add(p)
    await db_session.commit()

    scanner = DedupScanner(
        service_manager=services,
        session_factory=session_factory,
        settings=Settings(DRY_RUN=True),
    )

    # Mock _scan_movies returning the same pair
    mock_pair = {
        "media_type": "movie",
        "title": "Movie B",
        "winner": {"media_type": "movie", "title": "Movie B", "file_path": "/movies/b_4k.mkv", "file_size_bytes": 20_000_000_000},
        "loser": {"media_type": "movie", "title": "Movie B", "file_path": "/movies/b_1080p.mkv", "file_size_bytes": 5_000_000_000},
        "space_saved": 5_000_000_000,
    }
    scanner._scan_movies = AsyncMock(return_value=[mock_pair])
    scanner._scan_episodes = AsyncMock(return_value=[])

    result = await scanner.run_full_scan()
    assert result["status"] == "completed"

    # Verify no new PENDING_REVIEW pairs were created
    pending_pairs = list((await db_session.execute(
        select(DuplicatePair).where(DuplicatePair.status == DuplicatePairStatus.PENDING_REVIEW)
    )).scalars().all())
    assert len(pending_pairs) == 0


def test_plex_parse_media_item_filters_deleted_and_extracts_guids() -> None:
    from app.services.plex import PlexClient

    client = PlexClient(url="http://localhost:32400", token="dummy")
    metadata = {
        "ratingKey": "12345",
        "title": "Sample Movie",
        "year": 2023,
        "type": "movie",
        "Guid": [
            {"id": "tmdb://998877"},
            {"id": "imdb://tt776655"},
            {"id": "tvdb://112233"},
        ],
        "Media": [
            {
                "id": 1,
                "videoResolution": "2160",
                "Part": [{"id": 10, "file": "/movies/sample.2160p.mkv", "size": 30000000}],
            },
            {
                "id": 2,
                "deletedAt": 1730000000,  # Trashed media
                "videoResolution": "1080",
                "Part": [{"id": 20, "file": "/movies/sample.1080p.mkv", "size": 10000000}],
            },
            {
                "id": 3,
                "videoResolution": "720",
                "Part": [
                    {"id": 30, "file": "/movies/sample.720p.mkv", "size": 5000000, "deletedAt": 1730000001}  # Trashed part
                ],
            },
        ],
    }

    parsed = client.parse_media_item(metadata)
    # Only media 1 should be parsed because media 2 and part 3 have deletedAt
    assert len(parsed) == 1
    item = parsed[0]
    assert item.file_path == "/movies/sample.2160p.mkv"
    assert item.tmdb_id == 998877
    assert item.imdb_id == "tt776655"
    assert item.tvdb_id == 112233
