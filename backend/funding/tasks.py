import logging

from celery import shared_task

from funding.recurring import post_due_recurring_debits


@shared_task
def run_due_recurring_debits() -> int:
    logger = logging.getLogger("lotneeti.jobs")
    try:
        count = post_due_recurring_debits()
    except Exception as exc:
        logger.error(
            "job.failed",
            extra={
                "event": "job.failed",
                "job": "recurring_debits",
                "error_type": type(exc).__name__,
            },
        )
        raise
    logger.info(
        "job.completed", extra={"event": "job.completed", "job": "recurring_debits", "count": count}
    )
    return count
