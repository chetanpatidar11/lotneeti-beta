"""Generate private exports and recheck access before every download link."""

from hashlib import sha256
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import WorkspaceMembership
from core.audit import record_event
from core.beta_events import record_beta_event
from core.models import BetaEvent
from exports.models import PlanExport
from exports.services import export_saved_plan
from exports.storage import DOWNLOAD_TTL_SECONDS
from ipos.models import IPO


def _can_export(workspace, actor) -> bool:
    return WorkspaceMembership.objects.filter(
        workspace=workspace,
        user=actor,
        role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.OPERATOR),
    ).exists()


def generate_plan_export(
    *, plan_run, actor, storage, format_id="generic_csv", ipo_id=None
) -> PlanExport:
    artifact = export_saved_plan(plan_run=plan_run, actor=actor, format_id=format_id, ipo_id=ipo_id)
    export_rows = plan_run.rows.filter(ipo_ref=ipo_id) if ipo_id else plan_run.rows.all()
    filename = ""
    if format_id == "demat_csv":
        ipo = IPO.objects.get(pk=ipo_id)
        issuer = slugify(ipo.issuer_name)[:100] or "ipo"
        filename = f"demat-{issuer}-{timezone.localdate().isoformat()}.{artifact.extension}"
    export_id = uuid4()
    key = f"exports/{plan_run.workspace_id}/{plan_run.pk}/{export_id}.{artifact.extension}"
    storage.put(key, artifact)
    with transaction.atomic():
        record = PlanExport.objects.create(
            id=export_id,
            plan_run=plan_run,
            created_by=actor,
            format_id=artifact.format_id,
            format_version=artifact.format_version,
            content_type=artifact.content_type,
            object_key=key,
            download_filename=filename,
            ipo_ref=ipo_id or "",
            content_sha256=sha256(artifact.data).hexdigest(),
            planner_version=plan_run.planner_version,
            settings_version=plan_run.settings_version,
            input_snapshot_hash=plan_run.input_snapshot_hash,
            plan_output_hash=plan_run.output_hash,
            row_count=export_rows.count(),
            planned_total=export_rows.aggregate(total=Sum("amount"))["total"],
        )
        record_event(
            action="planner.export.generated",
            target=record,
            actor=actor,
            workspace=plan_run.workspace,
            metadata={"format": record.format_id, "version": record.format_version},
        )
        record_beta_event(workspace=plan_run.workspace, event_type=BetaEvent.Type.EXPORT_GENERATED)
    return record


def signed_export_download(*, record: PlanExport, actor, storage) -> tuple[str, int]:
    if not _can_export(record.plan_run.workspace, actor):
        raise ValidationError("This member cannot download the export")
    filename = (
        record.download_filename
        or f"lotneeti-plan-{record.plan_run_id}.{record.object_key.rsplit('.', 1)[-1]}"
    )
    url = storage.signed_url(record.object_key, filename=filename)
    record_event(
        action="planner.export.download_requested",
        target=record,
        actor=actor,
        workspace=record.plan_run.workspace,
        metadata={"format": record.format_id},
    )
    return url, DOWNLOAD_TTL_SECONDS
