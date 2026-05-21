from src.logger import get_logger

log = get_logger("notifier")


def notify(new_jobs: int, high_priority: int = 0) -> None:
    if new_jobs == 0:
        return
    title = "Physician Job Tracker"
    msg = f"{new_jobs} new jobs found"
    if high_priority:
        msg += f" ({high_priority} HIGH priority)"

    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=msg,
            app_name="Physician Job Tracker",
            timeout=10,
        )
    except Exception as e:
        log.warning(f"Desktop notification failed: {e}")

    log.info(f"[NOTIFICATION] {title}: {msg}")
