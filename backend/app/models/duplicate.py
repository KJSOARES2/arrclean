"""ORM models for duplicate media records and duplicate pairs."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DuplicateRecord(Base):
    """A single media file detected as part of a duplicate set.

    Each record captures comprehensive metadata about the file including
    resolution, HDR format, source type, audio/video codecs, file size,
    and integration IDs from Plex/Radarr/Sonarr.
    """

    __tablename__ = "duplicate_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── Media identification ────────────────────────────────────────────
    media_type: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="'movie' or 'episode'"
    )
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tvdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imdb_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    edition: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="e.g. 'Theatrical', 'Director\\'s Cut', 'Extended'",
    )

    # ── File details ────────────────────────────────────────────────────
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # ── Quality attributes ──────────────────────────────────────────────
    resolution: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="e.g. '2160p', '1080p', '720p'"
    )
    hdr_format: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="e.g. 'Dolby Vision', 'HDR10+', 'HDR10', 'SDR'"
    )
    source_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="e.g. 'Bluray', 'WEB-DL', 'Remux', 'HDTV'"
    )
    audio_codec: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="e.g. 'TrueHD Atmos', 'DTS-HD MA', 'AAC'"
    )
    video_codec: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="e.g. 'x265', 'x264', 'AV1'"
    )
    video_bitrate: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="Video bitrate in bits per second"
    )

    # ── Scores from *arr / calculated ───────────────────────────────────
    custom_format_score: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Custom format score from Radarr/Sonarr"
    )
    quality_profile_rank: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Rank within the quality profile"
    )
    composite_quality_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="ArrClean calculated quality score"
    )

    # ── External integration IDs ────────────────────────────────────────
    plex_rating_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    radarr_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sonarr_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sonarr_episode_file_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Hardlink / torrent info ─────────────────────────────────────────
    is_hardlinked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    inode_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    torrent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── Timestamps ──────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    # ── Relationships ───────────────────────────────────────────────────
    won_pairs: Mapped[list["DuplicatePair"]] = relationship(
        "DuplicatePair",
        foreign_keys="DuplicatePair.winner_record_id",
        back_populates="winner",
        lazy="selectin",
    )
    lost_pairs: Mapped[list["DuplicatePair"]] = relationship(
        "DuplicatePair",
        foreign_keys="DuplicatePair.loser_record_id",
        back_populates="loser",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_dup_rec_media_type", "media_type"),
        Index("ix_dup_rec_tmdb", "tmdb_id"),
        Index("ix_dup_rec_tvdb", "tvdb_id"),
        Index("ix_dup_rec_file_path", "file_path"),
    )

    def __repr__(self) -> str:
        return (
            f"<DuplicateRecord(id={self.id}, title='{self.title}', "
            f"resolution='{self.resolution}', score={self.composite_quality_score})>"
        )


class DuplicatePairStatus(str, enum.Enum):
    """Lifecycle status of a duplicate pair."""

    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    SEED_LOCKED = "SEED_LOCKED"
    COMPLETED = "COMPLETED"
    IGNORED = "IGNORED"
    ERROR = "ERROR"


class ActionTaken(str, enum.Enum):
    """Action performed on the losing file."""

    NONE = "NONE"
    DELETED = "DELETED"
    HARDLINK_REMOVED = "HARDLINK_REMOVED"
    SEED_LOCK_QUEUED = "SEED_LOCK_QUEUED"


class DuplicatePair(Base):
    """A pair of duplicate media files with a designated winner and loser.

    The winner is the higher-quality file that will be kept; the loser is
    the file scheduled for removal.
    """

    __tablename__ = "duplicate_pairs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    media_type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tvdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Winner / Loser foreign keys ─────────────────────────────────────
    winner_record_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("duplicate_records.id", ondelete="CASCADE"), nullable=False
    )
    loser_record_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("duplicate_records.id", ondelete="CASCADE"), nullable=False
    )

    # ── Status tracking ─────────────────────────────────────────────────
    status: Mapped[DuplicatePairStatus] = mapped_column(
        Enum(DuplicatePairStatus, native_enum=False, length=32),
        nullable=False,
        default=DuplicatePairStatus.PENDING_REVIEW,
    )
    action_taken: Mapped[ActionTaken] = mapped_column(
        Enum(ActionTaken, native_enum=False, length=32),
        nullable=False,
        default=ActionTaken.NONE,
    )
    space_saved_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # ── Timestamps ──────────────────────────────────────────────────────
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # ── Relationships ───────────────────────────────────────────────────
    winner: Mapped[DuplicateRecord] = relationship(
        "DuplicateRecord",
        foreign_keys=[winner_record_id],
        back_populates="won_pairs",
        lazy="selectin",
    )
    loser: Mapped[DuplicateRecord] = relationship(
        "DuplicateRecord",
        foreign_keys=[loser_record_id],
        back_populates="lost_pairs",
        lazy="selectin",
    )
    seed_lock_entries: Mapped[list["SeedLockEntry"]] = relationship(
        "SeedLockEntry",
        back_populates="duplicate_pair",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_dup_pair_status", "status"),
        Index("ix_dup_pair_media_type", "media_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<DuplicatePair(id={self.id}, title='{self.title}', "
            f"status={self.status.value})>"
        )


# Prevent circular import issues – SeedLockEntry imports are resolved via
# string-based relationship references above.
from app.models.seed_lock import SeedLockEntry as _SeedLockEntry  # noqa: E402, F401
