import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "supermarket",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks"],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Jerusalem",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
)

app.conf.beat_schedule = {
    "scrape-and-parse-every-3h": {
        "task": "app.tasks.scrape_and_parse",
        "schedule": crontab(minute=0, hour="*/3"),
        "kwargs": {"skip_blocked": True},
    },
    "full-scrape-nightly": {
        "task": "app.tasks.scrape_and_parse",
        "schedule": crontab(minute=0, hour=2),
        "kwargs": {"skip_blocked": False},
    },
}
