"""APScheduler background jobs for scheduled deduplication, seed monitoring, and queue checks."""

from __future__ import annotations

import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.engine.dedup_scanner import DedupScanner
from app.engine.queue_interceptor import QueueInterceptor
from app.engine.seed_monitor import SeedMonitor
from app.models.job_history import JobType

logger = logging.getLogger("arrclean.scheduler")

scheduler = AsyncIOScheduler()


async def scheduled_full_scan() -> None:
    """Scheduled cron task to scan the library for duplicates."""
    logger.info("Executing scheduled full library deduplication scan...")
    try:
        scanner = DedupScanner()
        res = await scanner.run_full_scan(job_type=JobType.FULL_SCAN)
        logger.info("Scheduled scan finished: %s", res)
    except Exception as e:
        logger.exception("Scheduled full scan failed: %s", e)


async def scheduled_seed_monitor() -> None:
    """Periodic task checking whether seed-locked items met retention rules."""
    logger.debug("Executing scheduled seed monitor check...")
    try:
        monitor = SeedMonitor()
        res = await monitor.check_seed_locks()
        if res.get("purged", 0) > 0:
            logger.info("Seed monitor purged %d torrents", res["purged"])
    except Exception as e:
        logger.exception("Scheduled seed monitor failed: %s", e)


async def scheduled_queue_interceptor() -> None:
    """Periodic task intercepting redundant downloads in queues."""
    logger.debug("Executing scheduled download queue interception check...")
    try:
        interceptor = QueueInterceptor()
        res = await interceptor.check_queues()
        if res.get("cancelled", 0) > 0:
            logger.info("Queue interceptor cancelled %d downloads", res["cancelled"])
    except Exception as e:
        logger.exception("Scheduled queue check failed: %s", e)


def start_scheduler() -> None:
    """Configure and start the APScheduler instance."""
    settings = get_settings()

    # 1. Full scan job (Cron)
    try:
        cron_trigger = CronTrigger.from_crontab(settings.SCAN_CRON)
        scheduler.add_job(
            scheduled_full_scan,
            trigger=cron_trigger,
            id="full_dedup_scan",
            name="Daily Library Deduplication Scan",
            replace_existing=True,
        )
        logger.info("Scheduled full scan with cron: %s", settings.SCAN_CRON)
    except Exception as e:
        logger.error("Failed to parse SCAN_CRON '%s': %s", settings.SCAN_CRON, e)

    # 2. Seed monitor job (Interval)
    scheduler.add_job(
        scheduled_seed_monitor,
        trigger=IntervalTrigger(minutes=max(1, settings.SEED_MONITOR_INTERVAL_MINUTES)),
        id="seed_monitor_check",
        name="qBittorrent Seed-Lock Watchdog",
        replace_existing=True,
    )
    logger.info(
        "Scheduled seed monitor check every %d minutes",
        settings.SEED_MONITOR_INTERVAL_MINUTES,
    )

    # 3. Queue interceptor job (Interval)
    scheduler.add_job(
        scheduled_queue_interceptor,
        trigger=IntervalTrigger(minutes=max(1, settings.QUEUE_CHECK_INTERVAL_MINUTES)),
        id="queue_interceptor_check",
        name="Redundant Queue Interception Worker",
        replace_existing=True,
    )
    logger.info(
        "Scheduled queue interceptor check every %d minutes",
        settings.QUEUE_CHECK_INTERVAL_MINUTES,
    )

    scheduler.start()
    logger.info("ArrClean background scheduler started.")


def stop_scheduler() -> None:
    """Stop the scheduler during application shutdown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("ArrClean background scheduler shut down.")
