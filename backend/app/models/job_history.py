"""ORM models for scan job history and cleanup action logging."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobType(str, enum.Enum):
    """Type of scan/maintenance job."""

    FULL_SCAN = "FULL_SCAN"
    QUEUE_CHECK = "QUEUE_CHECK"
    SEED_MONITOR = "SEED_MONITOR"
    MANUAL = "MANUAL"


class JobStatus(str, enum.Enum):
    """Current status of a scan job."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ScanJob(Base):
    """Record of a scan or maintenance job run."""

    __tablename__ = "scan_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    job_type: Mapped[JobType] = mapped_column(
        Enum(JobType, native_enum=False, length=16),
        nullable=False,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=16),
        nullable=False,
        default=JobStatus.RUNNING,
    )

    # ── Timing ──────────────────────────────────────────────────────────
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Results ─────────────────────────────────────────────────────────
    duplicates_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicates_resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    space_reclaimed_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # ── Diagnostics ─────────────────────────────────────────────────────
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_output: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ScanJob(id={self.id}, type={self.job_type.value}, "
            f"status={self.status.value})>"
        )
