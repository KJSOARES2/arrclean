"""Tests for ArrClean REST API endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.models.base import Base


@pytest.fixture
async def client() -> AsyncClient:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    import app.database as app_db
    old_engine = app_db._engine
    old_factory = app_db._session_factory
    app_db._engine = engine
    app_db._session_factory = session_factory

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    app_db._engine = old_engine
    app_db._session_factory = old_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "ArrClean"


@pytest.mark.asyncio
async def test_dashboard_stats(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/dashboard/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_space_reclaimed_bytes" in data
    assert "pending_space_to_reclaim_bytes" in data
    assert "seed_locked_space_bytes" in data
    assert "pending_review_space_bytes" in data
    assert "duplicates_found_count" in data
    assert "seed_locked_count" in data


@pytest.mark.asyncio
async def test_list_duplicates_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/duplicates")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_get_settings(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "DRY_RUN" in data
    assert "MIN_SEED_RATIO" in data


@pytest.mark.asyncio
async def test_ssrf_metadata_blocked(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/connections/test",
        json={"service": "plex", "url": "http://169.254.169.254/latest/meta-data"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "Security validation" in data["error"]


@pytest.mark.asyncio
async def test_log_token_scrubbing() -> None:
    from app.api.websocket import scrub_sensitive_tokens

    msg = "Connecting with apikey=abc123456789 and X-Plex-Token: secrettoken123"
    scrubbed = scrub_sensitive_tokens(msg)
    assert "abc123456789" not in scrubbed
    assert "secrettoken123" not in scrubbed
    assert "••••••••" in scrubbed


@pytest.mark.asyncio
async def test_ssrf_metadata_domain_blocked(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/connections/test",
        json={"service": "plex", "url": "http://metadata.google.internal/computeMetadata/v1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "Cloud metadata" in data["error"] or "Security validation" in data["error"]


@pytest.mark.asyncio
async def test_notify_scan_complete_arguments() -> None:
    from app.services.notifications import NotificationService

    service = NotificationService()
    # Call with kwargs used in dedup_scanner.py - must not raise TypeError
    res = await service.notify_scan_complete(
        duplicates_found=5,
        duplicates_resolved=2,
        space_reclaimed_bytes=1073741824,
        error="Test warning",
    )
    assert isinstance(res, dict)


@pytest.mark.asyncio
async def test_connection_test_with_masked_token(client: AsyncClient) -> None:
    # Testing sonarr and radarr with masked token '••••••••' must not raise UnicodeEncodeError
    resp = await client.post(
        "/api/v1/connections/test",
        json={"service": "sonarr", "url": "http://127.0.0.1:8989", "apikey": "••••••••"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "sonarr"
    assert "ascii" not in (data.get("error") or "")

    resp_radarr = await client.post(
        "/api/v1/connections/test",
        json={"service": "radarr", "url": "http://127.0.0.1:7878", "apikey": "••••••••"},
    )
    assert resp_radarr.status_code == 200
    data_radarr = resp_radarr.json()
    assert data_radarr["service"] == "radarr"
    assert "ascii" not in (data_radarr.get("error") or "")


@pytest.mark.asyncio
async def test_execute_approved_cleanups_endpoint(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/duplicates/execute-approved")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "executing"
    assert "message" in data


@pytest.mark.asyncio
async def test_seed_watch_endpoints_and_reconciliation(client: AsyncClient) -> None:
    # 1. Empty seed watch list
    resp = await client.get("/api/v1/seed-watch")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # 2. Add an orphaned SEED_LOCKED pair directly in DB
    import app.database as app_db
    from app.models.duplicate import DuplicatePair, DuplicatePairStatus, DuplicateRecord, ActionTaken
    from app.models.seed_lock import SeedLockEntry, SeedLockStatus

    async with app_db._session_factory() as session:
        win = DuplicateRecord(media_type="movie", title="Test Movie", file_path="/mock/path/win.mkv", file_size_bytes=2000)
        lose = DuplicateRecord(media_type="movie", title="Test Movie", file_path="/mock/path/lose.mkv", file_size_bytes=1000, torrent_hash="hash123")
        session.add(win)
        session.add(lose)
        await session.flush()

        pair = DuplicatePair(
            media_type="movie",
            title="Test Movie",
            winner_record_id=win.id,
            loser_record_id=lose.id,
            status=DuplicatePairStatus.SEED_LOCKED,
            space_saved_bytes=1000,
        )
        session.add(pair)
        await session.commit()

    # In default settings (DRY_RUN=True), calling seed-watch reconciles orphaned dry-run pair to APPROVED
    resp2 = await client.get("/api/v1/seed-watch")
    assert resp2.status_code == 200

    # Verify dashboard accurately reports stats without mismatch
    dash_resp = await client.get("/api/v1/dashboard/stats")
    assert dash_resp.status_code == 200
    dash_data = dash_resp.json()
    assert dash_data["seed_locked_count"] == 0

    # 3. Now insert an actual active SeedLockEntry
    async with app_db._session_factory() as session:
        pair.status = DuplicatePairStatus.SEED_LOCKED
        entry = SeedLockEntry(
            duplicate_pair_id=pair.id,
            torrent_hash="hash123",
            torrent_name="Test.Movie.2024.1080p",
            file_path="/mock/path/lose.mkv",
            current_ratio=0.5,
            target_ratio=1.0,
            current_seed_days=30,
            target_seed_days=90,
            status=SeedLockStatus.SEEDING,
        )
        session.add(entry)
        await session.commit()

    # Calling seed-watch returns the active entry with live progress
    resp3 = await client.get("/api/v1/seed-watch")
    assert resp3.status_code == 200
    items = resp3.json()
    assert len(items) == 1
    assert items[0]["torrent_name"] == "Test.Movie.2024.1080p"
    assert items[0]["current_ratio"] == 0.5
    assert items[0]["ratio_progress_percent"] == 50.0

    # Calling manual check endpoint succeeds
    check_resp = await client.post("/api/v1/seed-watch/check")
    assert check_resp.status_code == 200
    assert check_resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_qbittorrent_missing_torrent_handled_gracefully() -> None:
    from unittest.mock import AsyncMock, patch
    import httpx
    from app.services.qbittorrent import QBittorrentClient

    client = QBittorrentClient(url="http://127.0.0.1:8080", username="admin", password="password")

    # Mock 404 response on properties and files
    req = httpx.Request("GET", "http://127.0.0.1:8080/api/v2/torrents/properties?hash=missing123")
    resp_404 = httpx.Response(status_code=404, request=req)
    err_404 = httpx.HTTPStatusError("Client error '404 Not Found'", request=req, response=resp_404)

    with patch.object(client, "_request", new=AsyncMock(side_effect=err_404)):
        # 1. get_torrent_properties should return {} rather than raising 404
        props = await client.get_torrent_properties("missing123")
        assert props == {}

        # 2. get_torrent_files should return [] rather than raising 404
        files = await client.get_torrent_files("missing123")
        assert files == []

        # 3. delete_torrent should return True rather than raising 404
        del_res = await client.delete_torrent("missing123")
        assert del_res is True

    # 4. get_torrent_seeding_info should report can_delete=True, not_found=True
    with patch.object(client, "get_torrent_properties", new=AsyncMock(return_value={})):
        with patch.object(client, "get_torrents", new=AsyncMock(return_value=[])):
            seed_info = await client.get_torrent_seeding_info("missing123")
            assert seed_info["can_delete"] is True
            assert seed_info["not_found"] is True


@pytest.mark.asyncio
async def test_overseerr_and_prowlarr_connection_tests(client: AsyncClient) -> None:
    # Test overseerr and prowlarr connection test endpoints return valid schema
    resp_overseerr = await client.post(
        "/api/v1/connections/test",
        json={"service": "overseerr", "url": "http://127.0.0.1:5055", "apikey": "mockkey"},
    )
    assert resp_overseerr.status_code == 200
    assert resp_overseerr.json()["service"] == "overseerr"

    resp_prowlarr = await client.post(
        "/api/v1/connections/test",
        json={"service": "prowlarr", "url": "http://127.0.0.1:9696", "apikey": "mockkey"},
    )
    assert resp_prowlarr.status_code == 200
    assert resp_prowlarr.json()["service"] == "prowlarr"



