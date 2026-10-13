"""Discard temporary workbook contents after they are no longer needed."""

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from investors.models import AccountImportBatch


@shared_task
def purge_expired_account_import_previews() -> dict[str, int]:
    expired_at = timezone.now() - timedelta(hours=24)
    deleted, _ = AccountImportBatch.objects.filter(
        status=AccountImportBatch.Status.PREVIEWED,
        created_at__lt=expired_at,
    ).delete()
    scrubbed = (
        AccountImportBatch.objects.filter(
            status=AccountImportBatch.Status.CONFIRMED,
        )
        .exclude(rows_ciphertext="")
        .update(rows_ciphertext="")
    )
    return {"expired_previews": deleted, "confirmed_scrubbed": scrubbed}
