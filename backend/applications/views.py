from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
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
    cancel_application,
    edit_application,
    mark_allotted,
    mark_blocked,
    mark_not_allotted,
    mark_submitted,
    start_tracking_plan,
)
from funding.models import BankAccount, UPIHandle
from investors.models import Investor
from ipos.models import IPO
from ipos.overrides import effective_ipo_values, published_ipos
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


def _result(item, *, upper_price=None):
    sold_quantity = getattr(item, "sold_quantity", None)
    if sold_quantity is None:
        sold_quantity = item.sales.aggregate(total=Sum("quantity", default=0))["total"]
    return {
        "id": str(item.pk),
        "plan_row_id": str(item.plan_row_id),
        "is_plan_row": False,
        "ipo": str(item.ipo_id),
        "ipo_name": item.ipo.issuer_name,
        "applicant": str(item.applicant_id),
        "applicant_name": item.applicant.name,
        "bank": str(item.bank_id),
        "upi": str(item.upi_id) if item.upi_id else "",
        "bank_label": item.bank.bank_name
        if item.bank.is_imported_reference
        else f"{item.bank.bank_name} {item.bank.account_masked}",
        "upi_label": item.upi.handle if item.upi_id else "Bank ASBA",
        "close_date": item.ipo.close_date,
        "allotment_date": item.ipo.allotment_date,
        "sold_quantity": sold_quantity,
        "category": item.category,
        "lots": item.lots,
        "max_quantity": item.lots * item.ipo.lot_size,
        "upper_price": upper_price
        if upper_price is not None
        else str(effective_ipo_values(item.ipo)["upper_price"]),
        "amount": str(item.amount),
        "status": item.status,
        "planned_at": item.planned_at,
        "submitted_at": item.submitted_at,
        "blocked_at": item.blocked_at,
        "result_at": item.result_at,
        "edited_at": item.edited_at,
        "cancelled_at": item.cancelled_at,
        "allotted_quantity": item.allotted_quantity,
        "actual_cost": str(item.actual_cost) if item.actual_cost is not None else None,
    }


def _results(items):
    ipos = {item.ipo_id: item.ipo for item in items}
    prices = {pk: str(effective_ipo_values(ipo)["upper_price"]) for pk, ipo in ipos.items()}
    return [_result(item, upper_price=prices[item.ipo_id]) for item in items]


def _saved_plan_rows(workspace, tracked):
    """Show saved rows, including plans that still need review, without tracking them."""
    latest = PlanRun.objects.filter(workspace=workspace).first()
    if latest is None or latest.status not in {PlanRun.Status.READY, PlanRun.Status.BLOCKED}:
        return []
    rows = list(latest.rows.all())
    if latest.reserved_ipo_ids is not None:
        rows = [row for row in rows if row.ipo_ref in latest.reserved_ipo_ids]
    linked_rows = {item.plan_row_id for item in tracked}
    active_keys = {
        (
            str(item.ipo_id),
            str(item.applicant_id),
            "SHARE" if item.category == "SHARE" else "PUBLIC",
        )
        for item in tracked
        if item.status != Application.Status.CANCELLED
    }
    rows = [
        row
        for row in rows
        if row.pk not in linked_rows
        and (row.ipo_ref, row.applicant_ref, "SHARE" if row.category == "SHARE" else "PUBLIC")
        not in active_keys
    ]
    ipos = {str(item.pk): item for item in IPO.objects.filter(pk__in={r.ipo_ref for r in rows})}
    prices = {pk: str(effective_ipo_values(ipo)["upper_price"]) for pk, ipo in ipos.items()}
    investors = {
        str(item.pk): item
        for item in Investor.objects.filter(
            pk__in={r.applicant_ref for r in rows}, workspace=workspace, is_deleted=False
        )
    }
    banks = {
        str(item.pk): item
        for item in BankAccount.objects.filter(
            pk__in={r.bank_ref for r in rows}, workspace=workspace
        )
    }
    upis = {
        str(item.pk): item
        for item in UPIHandle.objects.filter(
            pk__in={r.upi_ref for r in rows if r.upi_ref}, bank__workspace=workspace
        )
    }
    result = []
    for row in rows:
        ipo = ipos.get(row.ipo_ref)
        investor = investors.get(row.applicant_ref)
        bank = banks.get(row.bank_ref)
        upi = upis.get(row.upi_ref)
        if not all((ipo, investor, bank)) or (upi is None and row.category != "BHNI"):
            continue
        result.append(
            {
                "id": str(row.pk),
                "plan_row_id": str(row.pk),
                "is_plan_row": True,
                "ipo": row.ipo_ref,
                "ipo_name": ipo.issuer_name,
                "applicant": row.applicant_ref,
                "applicant_name": investor.name,
                "bank": row.bank_ref,
                "bank_label": bank.bank_name
                if bank.is_imported_reference
                else f"{bank.bank_name} {bank.account_masked}",
                "upi": row.upi_ref,
                "upi_label": upi.handle if upi else "Bank ASBA",
                "close_date": ipo.close_date,
                "allotment_date": ipo.allotment_date,
                "sold_quantity": 0,
                "category": row.category,
                "lots": row.lots,
                "max_quantity": row.lots * ipo.lot_size,
                "upper_price": prices[row.ipo_ref],
                "amount": str(row.amount),
                "status": Application.Status.PLANNED,
                "planned_at": latest.generated_at,
                "submitted_at": None,
                "blocked_at": None,
                "result_at": None,
                "edited_at": None,
                "cancelled_at": None,
                "allotted_quantity": None,
                "actual_cost": None,
            }
        )
    return result


class RecordingRequestSerializer(serializers.Serializer):
    record_only = serializers.BooleanField(default=False)


class AllotmentSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)
    actual_cost = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01")
    )


class ApplicationEditSerializer(serializers.Serializer):
    def validate(self, attrs):
        if attrs.get("category") == "BHNI":
            if attrs.get("upi"):
                raise serializers.ValidationError("bHNI uses bank ASBA, without UPI.")
            attrs["upi"] = None
        elif not attrs.get("upi"):
            raise serializers.ValidationError("A linked UPI is required.")
        return attrs

    category = serializers.ChoiceField(choices=["RETAIL", "SHNI", "SHARE", "BHNI"])
    lots = serializers.IntegerField(min_value=1, max_value=100000)
    bank = serializers.UUIDField()
    upi = serializers.UUIDField(allow_null=True, required=False)


class ApplicationBulkSerializer(serializers.Serializer):
    record_only = serializers.BooleanField(default=False)
    action = serializers.ChoiceField(choices=["submit", "block", "cancel", "not-allotted"])
    ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=100)

    def validate_ids(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Choose each application only once.")
        return value


class TrackingRowsSerializer(serializers.Serializer):
    record_only = serializers.BooleanField(default=False)
    row_ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=1, max_length=100, required=False
    )

    def validate_row_ids(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Choose each planned application only once.")
        return value


class ApplicationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = _workspace(request, workspace_id)
        items = list(
            Application.objects.filter(workspace=workspace)
            .select_related("ipo", "applicant", "bank", "upi")
            .annotate(sold_quantity=Sum("sales__quantity", default=0))
        )
        return Response(_saved_plan_rows(workspace, items) + _results(items))


class StartTrackingView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workspace_id, run_id):
        workspace = _workspace(request, workspace_id)
        _writer(workspace, request.user)
        run = get_object_or_404(PlanRun.objects.filter(workspace=workspace), pk=run_id)
        serializer = TrackingRowsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if (
            "row_ids" in serializer.validated_data
            and PlanRun.objects.filter(workspace=workspace).first() != run
        ):
            return Response(
                {"detail": "This plan is no longer current. Refresh Applications."}, status=409
            )
        try:
            tracked = start_tracking_plan(
                plan_run=run,
                actor=request.user,
                row_ids=serializer.validated_data.get("row_ids"),
                record_only=serializer.validated_data["record_only"],
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=409)
        return Response(_results(tracked), status=201)


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
            "cancel": cancel_application,
        }
        if action not in (*actions, "allotted", "edit"):
            return Response({"detail": "Unknown application action."}, status=404)
        recording = RecordingRequestSerializer(data=request.data)
        recording.is_valid(raise_exception=True)
        record_only = recording.validated_data["record_only"]
        try:
            if action == "edit":
                serializer = ApplicationEditSerializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                changed = edit_application(
                    application=item,
                    actor=request.user,
                    category=serializer.validated_data["category"],
                    lots=serializer.validated_data["lots"],
                    bank_id=serializer.validated_data["bank"],
                    upi_id=serializer.validated_data.get("upi"),
                    record_only=record_only,
                )
            elif action == "allotted":
                serializer = AllotmentSerializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                changed = mark_allotted(
                    application=item,
                    actor=request.user,
                    quantity=serializer.validated_data["quantity"],
                    actual_cost=serializer.validated_data["actual_cost"],
                )
            else:
                changed = actions[action](
                    application=item,
                    actor=request.user,
                    **({"record_only": record_only} if action in {"submit", "block"} else {}),
                )
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=409)
        return Response(_result(changed))


class ApplicationBulkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workspace_id):
        workspace = _workspace(request, workspace_id)
        _writer(workspace, request.user)
        serializer = ApplicationBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]
        ids = serializer.validated_data["ids"]
        actions = {
            "submit": mark_submitted,
            "block": mark_blocked,
            "cancel": cancel_application,
            "not-allotted": mark_not_allotted,
        }
        try:
            with transaction.atomic():
                items = list(
                    # UPI is optional for ASBA. PostgreSQL cannot lock the
                    # nullable side of its outer join; lock applications only.
                    Application.objects.select_for_update(of=("self",))
                    .select_related("ipo", "applicant", "bank", "upi")
                    .filter(workspace=workspace, pk__in=ids)
                    .order_by("pk")
                )
                if len(items) != len(ids):
                    return Response(
                        {"detail": "One or more applications are unavailable."}, status=404
                    )
                changed = [
                    actions[action](
                        application=item,
                        actor=request.user,
                        **(
                            {"record_only": serializer.validated_data["record_only"]}
                            if action in {"submit", "block"}
                            else {}
                        ),
                    )
                    for item in items
                ]
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=409)
        return Response(_results(changed))


class WorkspaceOperationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = _workspace(request, workspace_id)
        today = timezone.localdate()
        applications = Application.objects.filter(workspace=workspace).exclude(
            status=Application.Status.CANCELLED
        )
        sales = list(
            Sale.objects.filter(application__workspace=workspace).select_related(
                "application__ipo", "application__applicant"
            )
        )
        return Response(
            {
                "active_ipos": published_ipos()
                .filter(
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
