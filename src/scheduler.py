import os
import threading

from apscheduler.schedulers.background import BackgroundScheduler

from src.logger import get_logger
from src.main import run_pipeline

log = get_logger("scheduler")
_scheduler: BackgroundScheduler | None = None
_lock = threading.Lock()


def start_scheduler(interval_hours: float | None = None) -> None:
    global _scheduler
    with _lock:
        if _scheduler and _scheduler.running:
            return
        hours = interval_hours or float(os.getenv("POLL_INTERVAL_HOURS", "2"))
        _scheduler = BackgroundScheduler()
        _scheduler.add_job(
            _run_job,
            "interval",
            hours=hours,
            id="pipeline",
            replace_existing=True,
        )
        _scheduler.start()
        log.info(f"Scheduler started — running every {hours}h")


def stop_scheduler() -> None:
    global _scheduler
    with _lock:
        if _scheduler and _scheduler.running:
            _scheduler.shutdown(wait=False)
            log.info("Scheduler stopped")


def get_next_run_time() -> str | None:
    if _scheduler and _scheduler.running:
        job = _scheduler.get_job("pipeline")
        if job and job.next_run_time:
            return job.next_run_time.strftime("%Y-%m-%d %H:%M UTC")
    return None


def is_running() -> bool:
    return bool(_scheduler and _scheduler.running)


def _run_job() -> None:
    log.info("Scheduled pipeline run starting...")
    try:
        run_pipeline()
    except Exception as e:
        log.error(f"Scheduled run failed: {e}")
