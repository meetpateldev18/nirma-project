"""
Celery Task Definitions — Outbound Call Dispatcher & Retries.

This module implements periodic background tasks for campaign scheduling:
1. dispatch_due_calls: Polls PostgreSQL for due call tasks and dispatches PSTN calls.
2. place_call_task: Worker task executing an outbound Plivo call for a single student.
3. retry_no_answer_calls: Reschedules unanswered calls based on campaign retry limits.
4. cleanup_old_sessions: Purges stale static audio cache files older than 30 days.

TRAI REGULATORY COMPLIANCE:
    Automated calls are strictly restricted to 09:00:00 - 21:00:00 IST. Outside
    this window, dispatch_due_calls will defer execution until the next business morning.

Dependencies:
    - celery >= 5.4
    - backend.telephony.plivo_adapter
"""

import asyncio
import datetime
import logging
import os
import time
from typing import Optional
import pytz

from backend.config import settings
from backend.database.models import CallCampaign, CallTask, utc_now
from backend.database.session import get_sync_session
from backend.scheduler.celery_app import celery_app
from backend.telephony import get_telephony_adapter

logger = logging.getLogger(__name__)

IST_TIMEZONE = pytz.timezone("Asia/Kolkata")


def is_within_trai_calling_window() -> bool:
    """
    Verifies if current Indian Standard Time (IST) is within allowed calling hours (9 AM - 9 PM).

    Returns:
        bool: True if allowed to place automated calls, False otherwise.
    """
    now_ist = datetime.datetime.now(IST_TIMEZONE)
    start_time = now_ist.replace(hour=9, minute=0, second=0, microsecond=0)
    end_time = now_ist.replace(hour=21, minute=0, second=0, microsecond=0)
    return start_time <= now_ist <= end_time


@celery_app.task
def dispatch_due_calls() -> int:
    """
    Periodic beat task running every 30 seconds to poll and queue due call tasks.

    Checks TRAI calling window, selects up to 10 pending tasks scheduled on or before
    the current time, and queues place_call_task jobs for execution.

    Concurrency Guarantees:
        - Upstash Redis distributed lock (TTL=25s) prevents concurrent overlapping ticks.
        - PostgreSQL 'FOR UPDATE SKIP LOCKED' prevents thread contention across multiple workers.

    Returns:
        int: Number of call tasks queued in this execution tick.
    """
    if not is_within_trai_calling_window():
        logger.info("Outside TRAI calling window (09:00 - 21:00 IST). Deferring call dispatch.")
        return 0

    import redis
    redis_lock_client = redis.from_url(settings.redis_url, socket_timeout=3.0)
    lock_acquired = redis_lock_client.set("lock:dispatcher:batch", "active", nx=True, ex=25)
    if not lock_acquired:
        logger.info("Another dispatcher batch task is currently executing. Skipping this tick.")
        return 0

    dispatched_count = 0
    try:
        with get_sync_session() as db:
            now_utc = utc_now()
            # SKIP LOCKED guarantees non-blocking queue processing across concurrent workers
            due_tasks = (
                db.query(CallTask)
                .filter(CallTask.status == "pending", CallTask.scheduled_at <= now_utc)
                .order_by(CallTask.scheduled_at.asc())
                .limit(10)
                .with_for_update(skip_locked=True)
                .all()
            )

            for task in due_tasks:
                # Mark task as ringing to prevent duplicate pickup by concurrent ticks
                task.status = "ringing"
                dispatched_count += 1
                db.commit()

                # Trigger asynchronous Celery task
                place_call_task.delay(task.id)
                logger.info("Queued place_call_task for CallTask ID %d (To: %s)", task.id, task.student_phone)
    finally:
        try:
            redis_lock_client.delete("lock:dispatcher:batch")
        except Exception:
            pass

    return dispatched_count


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def place_call_task(self, call_task_id: int) -> Optional[str]:
    """
    Worker task to initiate an outbound PSTN call via Plivo API for a single recipient.

    Args:
        call_task_id: Primary key ID of the CallTask record in database.

    Returns:
        Optional[str]: Plivo request/call UUID if successfully placed.
    """
    logger.info("Executing place_call_task for Task ID: %d", call_task_id)

    with get_sync_session() as db:
        task = db.query(CallTask).filter(CallTask.id == call_task_id).first()

        if not task:
            logger.error("CallTask ID %d not found in database.", call_task_id)
            return None

        # Verify task is in dispatchable state
        if task.status not in ["pending", "ringing"]:
            logger.warning("CallTask ID %d has status '%s'. Skipping call placement.", call_task_id, task.status)
            return None

        # Build dynamic callback URLs bound to Nirma institutional domain for active carrier
        carrier = settings.telephony_provider.strip().lower()
        webhook_urls = settings.get_carrier_webhook_urls(call_task_id)
        answer_url = webhook_urls["answer_url"]
        hangup_url = webhook_urls["hangup_url"]

        adapter = get_telephony_adapter(carrier)
        caller_id = settings.active_caller_id

        try:
            # Execute telephony carrier REST call synchronously with zero asyncio event loop overhead
            result = adapter.place_call_sync(
                to_number=task.student_phone,
                answer_url=answer_url,
                hangup_url=hangup_url,
                caller_id=caller_id,
            )

            if result.status == "queued":
                task.status = "ringing"
                task.plivo_uuid = result.call_uuid
                task.placed_at = utc_now()
                db.commit()
                logger.info(
                    "Call successfully dispatched via %s -> TaskID: %d, CarrierUUID: %s",
                    carrier.upper(),
                    call_task_id,
                    result.call_uuid,
                )
                return result.call_uuid
            else:
                task.status = "failed"
                task.outcome = "failed"
                db.commit()
                logger.error("Plivo dispatch failed for TaskID %d: %s", call_task_id, result.error)
                raise self.retry(exc=Exception(result.error))

        except Exception as exc:
            logger.error("Error executing place_call_task for TaskID %d: %s", call_task_id, exc)
            task.status = "failed"
            task.outcome = "failed"
            db.commit()
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc)
            return None


@celery_app.task
def retry_no_answer_calls() -> int:
    """
    Periodic task running every 15 minutes to reschedule unanswered calls.

    Checks CallTask records with outcome 'no_answer' where retry_count < campaign.max_retries.

    Returns:
        int: Number of tasks rescheduled.
    """
    rescheduled_count = 0
    with get_sync_session() as db:
        tasks_to_retry = (
            db.query(CallTask, CallCampaign)
            .join(CallCampaign, CallTask.campaign_id == CallCampaign.id)
            .filter(
                CallTask.status == "completed",
                CallTask.outcome == "no_answer",
                CallTask.retry_count < CallCampaign.max_retries,
            )
            .all()
        )

        for task, campaign in tasks_to_retry:
            delay_minutes = campaign.retry_delay_min or 60
            task.retry_count += 1
            task.status = "pending"
            task.outcome = None
            task.scheduled_at = utc_now() + datetime.timedelta(minutes=delay_minutes)
            rescheduled_count += 1
            logger.info(
                "Rescheduled CallTask ID %d (Retry %d/%d) for %s",
                task.id,
                task.retry_count,
                campaign.max_retries,
                task.scheduled_at,
            )
        db.commit()

    return rescheduled_count


@celery_app.task
def cleanup_old_sessions() -> int:
    """
    Daily maintenance task to delete cached audio files older than 30 days.

    Returns:
        int: Number of deleted files.
    """
    cache_dir = settings.audio_cache_dir
    if not os.path.exists(cache_dir):
        return 0

    deleted_count = 0
    cutoff_seconds = time.time() - (30 * 86400)  # 30 Days ago

    for filename in os.listdir(cache_dir):
        file_path = os.path.join(cache_dir, filename)
        if os.path.isfile(file_path):
            if os.path.getmtime(file_path) < cutoff_seconds:
                try:
                    os.unlink(file_path)
                    deleted_count += 1
                except Exception as exc:
                    logger.error("Failed to delete stale cache file %s: %s", file_path, exc)

    logger.info("Purged %d stale audio cache files from %s", deleted_count, cache_dir)
    return deleted_count
