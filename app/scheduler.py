from apscheduler.schedulers.background import BackgroundScheduler
from .config import CHECK_INTERVAL_MINUTES
from .publisher import run_once

scheduler = BackgroundScheduler(timezone="America/Mazatlan")


def scheduled_job():
    try:
        result = run_once()
        print("NewsAuto result:", result)
    except Exception as exc:
        print("NewsAuto error:", exc)


def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(
            scheduled_job,
            "interval",
            minutes=CHECK_INTERVAL_MINUTES,
            id="news_auto_job",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.start()
