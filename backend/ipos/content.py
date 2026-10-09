"""Provider-neutral IPO summary storage and reviewed publication workflow."""

from django.core.exceptions import ValidationError
from django.db import transaction

from core.audit import record_event
from ipos.models import IPOContentRevision, IPOContentVersion


def queue_content_version(
    *,
    ipo,
    content_type: str,
    source_document_id: str,
    draft_text: str,
    provider_key: str = "manual",
    model_name: str = "",
    prompt_version: str = "",
    source_document_url: str = "",
    source_payload_hash: str = "",
):
    if content_type not in IPOContentVersion.ContentType.values:
        raise ValidationError("Unknown IPO summary type")
    if not source_document_id.strip() or not provider_key.strip():
        raise ValidationError("Document and provider identifiers are required")
    if not draft_text.strip() or len(draft_text) > 20000:
        raise ValidationError("A draft summary is required")
    version, created = IPOContentVersion.objects.get_or_create(
        ipo=ipo,
        content_type=content_type,
        source_document_id=source_document_id.strip(),
        provider_key=provider_key.strip(),
        model_name=model_name.strip(),
        defaults={
            "source_document_url": source_document_url,
            "source_payload_hash": source_payload_hash,
            "prompt_version": prompt_version,
            "draft_text": draft_text,
        },
    )
    return version, created


@transaction.atomic
def publish_content_revision(*, version: IPOContentVersion, text: str, reason: str, actor):
    text = text.strip()
    reason = reason.strip()
    if not text or len(text) > 20000:
        raise ValidationError("Published summary text is required")
    if not reason or len(reason) > 500:
        raise ValidationError("A reason of up to 500 characters is required")
    locked = IPOContentVersion.objects.select_for_update().get(pk=version.pk)
    revision = IPOContentRevision.objects.create(
        content_version=locked,
        text=text,
        reason=reason,
        created_by=actor,
    )
    locked.review_state = IPOContentVersion.ReviewState.REVIEWED
    locked.reviewed_at = revision.created_at
    locked.reviewed_by = actor
    locked.save(update_fields=["review_state", "reviewed_at", "reviewed_by"])
    record_event(
        action="ipo.content_published",
        target=revision,
        actor=actor,
        metadata={
            "content_type": locked.content_type,
            "source_document_id": locked.source_document_id,
        },
    )
    return revision


def published_summary(ipo, content_type: str):
    versions = ipo.content_versions.filter(
        content_type=content_type, review_state=IPOContentVersion.ReviewState.REVIEWED
    ).prefetch_related("revisions")
    revisions = [revision for version in versions for revision in version.revisions.all()]
    if not revisions:
        return None
    return max(revisions, key=lambda item: (item.created_at, item.pk)).text
