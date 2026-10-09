from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import WorkspaceMembership
from exports.models import PlanExport
from exports.operations import generate_plan_export, signed_export_download
from exports.storage import get_export_storage
from planner.models import PlanRun


def _require_writer(workspace_id, user):
    if not WorkspaceMembership.objects.filter(
        workspace_id=workspace_id,
        user=user,
        role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.OPERATOR),
    ).exists():
        raise PermissionDenied("Only workspace owners and operators can export plans.")


class PlanExportCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workspace_id, run_id):
        run = get_object_or_404(
            PlanRun.objects.filter(
                workspace_id=workspace_id, workspace__memberships__user=request.user
            ),
            pk=run_id,
        )
        _require_writer(workspace_id, request.user)
        format_id = request.data.get("format_id", "generic_csv")
        if format_id != "generic_csv":
            return Response({"detail": "Unknown export format."}, status=400)
        try:
            record = generate_plan_export(
                plan_run=run,
                actor=request.user,
                storage=get_export_storage(),
                format_id=format_id,
            )
        except ImproperlyConfigured:
            return Response({"detail": "Private export storage is not configured."}, status=503)
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=409)
        return Response(
            {
                "id": str(record.pk),
                "plan_run": str(run.pk),
                "format_id": record.format_id,
                "format_version": record.format_version,
                "row_count": record.row_count,
                "planned_total": str(record.planned_total),
            },
            status=201,
        )


class PlanExportDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id, run_id, export_id):
        record = get_object_or_404(
            PlanExport.objects.select_related("plan_run").filter(
                plan_run_id=run_id,
                plan_run__workspace_id=workspace_id,
                plan_run__workspace__memberships__user=request.user,
            ),
            pk=export_id,
        )
        _require_writer(workspace_id, request.user)
        try:
            url, ttl = signed_export_download(
                record=record, actor=request.user, storage=get_export_storage()
            )
        except ImproperlyConfigured:
            return Response({"detail": "Private export storage is not configured."}, status=503)
        return Response({"download_url": url, "expires_in_seconds": ttl})
