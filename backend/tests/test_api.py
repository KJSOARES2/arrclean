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
    assert "duplicates_found_count" in data


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

