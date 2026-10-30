"""ORM model for the seed-lock completion queue.

When a duplicate's loser file is actively being seeded in qBittorrent,
it enters the seed-lock queue rather than being immediately deleted.
The seed monitor periodically checks whether the torrent has met its
seeding requirements before scheduling the file for purge.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
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


class SeedLockStatus(str, enum.Enum):
    """Status of a seed-locked entry."""

    SEEDING = "SEEDING"
    RATIO_MET = "RATIO_MET"
    TIME_MET = "TIME_MET"
    PURGED = "PURGED"
    ERROR = "ERROR"


class SeedLockEntry(Base):
    """A torrent held in the seed-lock queue pending ratio/time requirements."""

    __tablename__ = "seed_lock_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── Link to duplicate pair ──────────────────────────────────────────
    duplicate_pair_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("duplicate_pairs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ── Torrent identification ──────────────────────────────────────────
    torrent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    torrent_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(
        Text, nullable=False, comment="The file path inside qBittorrent"
    )

    # ── Seeding progress ────────────────────────────────────────────────
    current_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    target_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    current_seed_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_seed_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)

    # ── Status ──────────────────────────────────────────────────────────
    status: Mapped[SeedLockStatus] = mapped_column(
        Enum(SeedLockStatus, native_enum=False, length=16),
        nullable=False,
        default=SeedLockStatus.SEEDING,
    )
    estimated_unlock_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Timestamps ──────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    purged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ───────────────────────────────────────────────────
    duplicate_pair: Mapped["DuplicatePair"] = relationship(  # noqa: F821
        "DuplicatePair",
        back_populates="seed_lock_entries",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_seed_lock_status", "status"),
        Index("ix_seed_lock_torrent", "torrent_hash"),
    )

    def __repr__(self) -> str:
        return (
            f"<SeedLockEntry(id={self.id}, torrent='{self.torrent_name}', "
            f"ratio={self.current_ratio}/{self.target_ratio}, "
            f"status={self.status.value})>"
        )
