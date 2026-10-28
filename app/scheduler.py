from __future__ import annotations

from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from .checker import check_all
from .config import get_settings

_scheduler: BackgroundScheduler | None = None


def start() -> None:
    global _scheduler
    settings = get_settings()
    if not settings.scheduler_enabled or _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        check_all,
        trigger="interval",
        hours=settings.check_interval_hours,
        id="check-all",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now() + timedelta(seconds=45),
    )
    _scheduler.start()


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def next_run() -> datetime | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job("check-all")
    return job.next_run_time if job else None
