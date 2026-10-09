from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Workspace, WorkspaceMembership
from applications.models import Application
from applications.services import (
    mark_allotted,
    mark_blocked,
    mark_not_allotted,
    mark_submitted,
    start_tracking_plan,
)
from ipos.models import IPO
from planner.models import PlanRun
from portfolio.models import Sale
from portfolio.reports import profit_report


def _workspace(request, workspace_id):
    return get_object_or_404(
        Workspace.objects.filter(memberships__user=request.user), pk=workspace_id
    )


def _writer(workspace, user):
    if not WorkspaceMembership.objects.filter(
        workspace=workspace,
        user=user,
        role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.OPERATOR),
    ).exists():
        raise PermissionDenied("Only workspace owners and operators can update applications.")


def _result(item):
    sold_quantity = getattr(item, "sold_quantity", None)
    if sold_quantity is None:
        sold_quantity = item.sales.aggregate(total=Sum("quantity", default=0))["total"]
    return {
        "id": str(item.pk),
        "ipo": str(item.ipo_id),
        "ipo_name": item.ipo.issuer_name,
        "applicant": str(item.applicant_id),
        "applicant_name": item.applicant.name,
        "bank": str(item.bank_id),
        "bank_label": f"{item.bank.bank_name} {item.bank.account_masked}",
        "upi_label": item.upi.handle_masked,
        "close_date": item.ipo.close_date,
        "allotment_date": item.ipo.allotment_date,
        "sold_quantity": sold_quantity,
        "category": item.category,
        "lots": item.lots,
        "max_quantity": item.lots * item.ipo.lot_size,
        "amount": str(item.amount),
        "status": item.status,
        "planned_at": item.planned_at,
        "submitted_at": item.submitted_at,
        "blocked_at": item.blocked_at,
        "result_at": item.result_at,
        "allotted_quantity": item.allotted_quantity,
        "actual_cost": str(item.actual_cost) if item.actual_cost is not None else None,
    }


class AllotmentSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)
    actual_cost = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01")
    )


class ApplicationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = _workspace(request, workspace_id)
        items = (
            Application.objects.filter(workspace=workspace)
            .select_related("ipo", "applicant", "bank", "upi")
            .annotate(sold_quantity=Sum("sales__quantity", default=0))
        )
        return Response([_result(item) for item in items])


class StartTrackingView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workspace_id, run_id):
        workspace = _workspace(request, workspace_id)
        _writer(workspace, request.user)
        run = get_object_or_404(PlanRun.objects.filter(workspace=workspace), pk=run_id)
        try:
            tracked = start_tracking_plan(plan_run=run, actor=request.user)
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=409)
        return Response([_result(item) for item in tracked], status=201)


class ApplicationActionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workspace_id, application_id, action):
        workspace = _workspace(request, workspace_id)
        _writer(workspace, request.user)
        item = get_object_or_404(
            Application.objects.select_related("ipo", "applicant", "bank", "upi").filter(
                workspace=workspace
            ),
            pk=application_id,
        )
        actions = {
            "submit": mark_submitted,
            "block": mark_blocked,
            "not-allotted": mark_not_allotted,
        }
        if action not in (*actions, "allotted"):
            return Response({"detail": "Unknown application action."}, status=404)
        try:
            if action == "allotted":
                serializer = AllotmentSerializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                changed = mark_allotted(
                    application=item,
                    actor=request.user,
                    quantity=serializer.validated_data["quantity"],
                    actual_cost=serializer.validated_data["actual_cost"],
                )
            else:
                changed = actions[action](application=item, actor=request.user)
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=409)
        return Response(_result(changed))


class WorkspaceOperationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = _workspace(request, workspace_id)
        today = timezone.localdate()
        applications = Application.objects.filter(workspace=workspace)
        sales = list(
            Sale.objects.filter(application__workspace=workspace).select_related(
                "application__ipo", "application__applicant"
            )
        )
        return Response(
            {
                "active_ipos": IPO.objects.filter(
                    publication_state=IPO.PublicationState.PUBLISHED,
                    open_date__lte=today,
                    close_date__gte=today,
                )
                .exclude(status=IPO.Status.CANCELLED)
                .count(),
                "applications": applications.count(),
                "pending_mandates": applications.filter(
                    status=Application.Status.SUBMITTED
                ).count(),
                "allotment_wins": applications.filter(status=Application.Status.ALLOTTED).count(),
                "realized_gains": profit_report(sales)["workspace"]["realized_profit"],
            }
        )
