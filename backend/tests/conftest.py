"""Shared fixtures for ArrClean tests."""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.engine.quality_scorer import (
    AudioCodec,
    HDRFormat,
    MediaQualityInfo,
    QualityScorer,
    QualityWeights,
    Resolution,
    SourceType,
    VideoCodec,
)
from app.models.base import Base


@pytest.fixture
def quality_scorer() -> QualityScorer:
    """Default quality scorer with standard weights."""
    return QualityScorer()


@pytest.fixture
def custom_scorer() -> QualityScorer:
    """Quality scorer with custom weights."""
    return QualityScorer(
        weights=QualityWeights(
            resolution=2.0, hdr=1.5, audio=1.0, source=1.0, codec=1.0
        )
    )


@pytest.fixture
def sample_4k_remux() -> MediaQualityInfo:
    """A high-quality 4K Remux file."""
    return MediaQualityInfo(
        resolution=Resolution.UHD_4K,
        hdr_format=HDRFormat.DOLBY_VISION,
        source_type=SourceType.REMUX,
        audio_codec=AudioCodec.TRUEHD_ATMOS,
        video_codec=VideoCodec.H265,
        video_bitrate_kbps=60000,
        custom_format_score=8450,
        file_size_bytes=45_200_000_000,  # ~45 GB
    )


@pytest.fixture
def sample_1080p_webdl() -> MediaQualityInfo:
    """A standard 1080p WEB-DL file."""
    return MediaQualityInfo(
        resolution=Resolution.HD_1080P,
        hdr_format=HDRFormat.SDR,
        source_type=SourceType.WEB_DL,
        audio_codec=AudioCodec.EAC3,
        video_codec=VideoCodec.H265,
        video_bitrate_kbps=8000,
        custom_format_score=1200,
        file_size_bytes=12_800_000_000,  # ~12.8 GB
    )


@pytest.fixture
def sample_4k_sdr() -> MediaQualityInfo:
    """A 4K SDR file (should lose to 4K HDR)."""
    return MediaQualityInfo(
        resolution=Resolution.UHD_4K,
        hdr_format=HDRFormat.SDR,
        source_type=SourceType.WEB_DL,
        audio_codec=AudioCodec.EAC3,
        video_codec=VideoCodec.H265,
        video_bitrate_kbps=15000,
        file_size_bytes=20_000_000_000,
    )


@pytest.fixture
def sample_720p_hdtv() -> MediaQualityInfo:
    """A low-quality 720p HDTV file."""
    return MediaQualityInfo(
        resolution=Resolution.HD_720P,
        hdr_format=HDRFormat.SDR,
        source_type=SourceType.HDTV,
        audio_codec=AudioCodec.AC3,
        video_codec=VideoCodec.H264,
        video_bitrate_kbps=4000,
        file_size_bytes=4_000_000_000,
    )


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite database session fixture."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()
