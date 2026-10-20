"""
Celery Task Queue & Beat Scheduler Configuration.

This module initializes the Celery app instance, configures message brokers,
enforces worker retry safety policies, and registers cron-style beat schedules:
- dispatch-due-calls: Runs every 30 seconds to poll and queue due call tasks.
- retry-no-answer: Runs every 15 minutes to reschedule unanswered calls.
- cleanup-old-sessions: Runs daily at 2:00 AM IST to purge expired audio files.

Dependencies:
    - celery >= 5.4
    - redis >= 5.0
"""

from celery import Celery
from celery.schedules import crontab

from backend.config import settings

# Initialize Celery app
celery_app = Celery(
    "nirma_call_agent",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["backend.scheduler.tasks"],
)

# Configure Celery serialization and worker execution invariants
celery_conf = {
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],
    "timezone": "Asia/Kolkata",
    "enable_utc": True,
    # Worker safety: Acknowledge late so lost worker tasks are re-queued automatically
    "task_acks_late": True,
    "task_reject_on_worker_lost": True,
    # Rate limits & concurrency controls
    "worker_prefetch_multiplier": 1,
    "task_time_limit": 300,        # Hard timeout: 5 minutes max per call dispatch
    "task_soft_time_limit": 240,   # Soft timeout warning: 4 minutes
}

import ssl
if settings.celery_broker_url.startswith("rediss://"):
    celery_conf["broker_use_ssl"] = {"ssl_cert_reqs": ssl.CERT_NONE}
if settings.celery_result_backend.startswith("rediss://"):
    celery_conf["redis_backend_use_ssl"] = {"ssl_cert_reqs": ssl.CERT_NONE}

celery_app.conf.update(celery_conf)

# Define Celery Beat periodic schedule
celery_app.conf.beat_schedule = {
    "dispatch-due-calls-every-30s": {
        "task": "backend.scheduler.tasks.dispatch_due_calls",
        "schedule": 30.0,  # Every 30 seconds
    },
    "retry-no-answer-calls-every-15m": {
        "task": "backend.scheduler.tasks.retry_no_answer_calls",
        "schedule": 900.0,  # Every 15 minutes
    },
    "cleanup-old-sessions-daily": {
        "task": "backend.scheduler.tasks.cleanup_old_sessions",
        "schedule": crontab(hour=2, minute=0),  # Daily at 02:00 AM IST
    },
}
