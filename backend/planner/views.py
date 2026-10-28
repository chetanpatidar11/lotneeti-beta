from dataclasses import asdict, replace

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Workspace, WorkspaceMembership
from accounts.permissions import WorkspaceDataPermission
from applications.models import Application
from core.beta_events import record_beta_event
from core.models import BetaEvent
from funding.models import BankAccount
from planner.capital import capital_totals
from planner.dto import LockedRowInput
from planner.models import PlanRun
from planner.persistence import clear_plan_run, create_reviewed_plan_run
from planner.plan_window import snapshot_is_planning_only
from planner.quota_planning import (
    generate_quota_proposal,
    quota_context,
    review_quota_rows,
    row_issue_codes,
)
from planner.snapshot_builder import build_snapshot


class CategoryMappingSerializer(serializers.Serializer):
    def validate(self, attrs):
        if attrs.get("category") == "BHNI":
            if attrs.get("upi"):
                raise serializers.ValidationError("bHNI uses bank ASBA, without UPI.")
            attrs["upi"] = None
        elif not attrs.get("upi"):
            raise serializers.ValidationError("A linked UPI is required for this category.")
        return attrs


class LockedRowSerializer(CategoryMappingSerializer):
    ipo = serializers.UUIDField()
    applicant = serializers.UUIDField()
    category = serializers.ChoiceField(choices=["RETAIL", "SHNI", "SHARE", "BHNI"])
    lots = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    demat = serializers.UUIDField()
    bank = serializers.UUIDField()
    upi = serializers.UUIDField(allow_null=True, required=False)


MAX_LOCKED_ROWS = 100
MAX_EDITED_ROWS = 500


class PreviewRequestSerializer(serializers.Serializer):
    ipo_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=True, max_length=100
    )
    locked_rows = LockedRowSerializer(many=True, required=False, max_length=MAX_LOCKED_ROWS)
    plan_cross_funding_override = serializers.ChoiceField(
        choices=["DEFAULT", "ALLOW", "WARN", "DISALLOW"], default="DEFAULT"
    )

    def validate_locked_rows(self, rows):
        seen = set()
        for row in rows:
            key = (
                row["ipo"],
                row["applicant"],
                "SHARE" if row["category"] == "SHARE" else "PUBLIC",
            )
            if key in seen:
                raise serializers.ValidationError(
                    "Keep one public and one shareholder application per applicant and IPO."
                )
            seen.add(key)
        return rows


class PlannerPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workspace_id):
        workspace = get_object_or_404(
            Workspace.objects.filter(memberships__user=request.user), pk=workspace_id
        )
        serializer = PreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requested = serializer.validated_data.get("ipo_ids")
        try:
            snapshot = build_snapshot(
                workspace=workspace,
                ipo_ids=frozenset(str(item) for item in requested)
                if requested is not None
                else None,
                plan_cross_funding_override=serializer.validated_data[
                    "plan_cross_funding_override"
                ],
            )
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        except ImproperlyConfigured:
            return Response({"detail": "Planner policy has not been configured."}, status=503)
        known = {
            "applicant": {item.id for item in snapshot.applicants},
            "demat": {item.id for item in snapshot.demats},
            "bank": {item.id for item in snapshot.banks},
            "upi": {item.id for item in snapshot.upis},
        }
        locks = []
        for position, item in enumerate(serializer.validated_data.get("locked_rows", [])):
            if any(
                str(item.get(field)) not in ids
                for field, ids in known.items()
                if not (field == "upi" and item["category"] == "BHNI" and not item.get("upi"))
            ):
                raise serializers.ValidationError(
                    {"locked_rows": "A locked mapping is outside this workspace."}
                )
            ipo_id = str(item["ipo"])
            if ipo_id not in {ipo.id for ipo in snapshot.ipos}:
                continue
            locks.append(
                LockedRowInput(
                    id=f"manual:{ipo_id}:{item['applicant']}:{position}",
                    ipo_id=ipo_id,
                    applicant_id=str(item["applicant"]),
                    category=item["category"],
                    lots=item["lots"],
                    amount=item["amount"],
                    demat_id=str(item["demat"]),
                    bank_id=str(item["bank"]),
                    upi_id=str(item["upi"]) if item.get("upi") else "",
                )
            )
        snapshot = replace(snapshot, locked_rows=tuple(locks))
        proposal = generate_quota_proposal(snapshot, quota_context(workspace, snapshot))
        record_beta_event(workspace=workspace, event_type=BetaEvent.Type.PLAN_GENERATED)
        return Response(
            {
                "planner_version": proposal.planner_version,
                "settings_version": proposal.settings_version,
                "input_snapshot_hash": proposal.input_snapshot_hash,
                "output_hash": proposal.output_hash,
                "status": "READY" if proposal.audit.valid else "BLOCKED",
                "planning_only": snapshot_is_planning_only(snapshot),
                "planned_total": str(proposal.audit.planned_total),
                "rows": [
                    {
                        "ipo": row.ipo_id,
                        "applicant": row.applicant_id,
                        "category": row.category,
                        "lots": row.lots,
                        "amount": str(row.amount),
                        "demat": row.demat_id,
                        "bank": row.bank_id,
                        "upi": row.upi_id,
                        "locked": row.locked,
                        "warnings": row.warnings,
                        "blocking_reasons": row.blocking_reasons,
                        "reasons": [asdict(reason) for reason in row.reasons],
                    }
                    for row in proposal.coverage.rows
                ],
                "uncovered": [asdict(item) for item in proposal.coverage.uncovered],
                "audit_issues": [asdict(item) for item in proposal.audit.issues],
            }
        )


class EditedRowSerializer(CategoryMappingSerializer):
    ipo = serializers.UUIDField()
    applicant = serializers.UUIDField()
    category = serializers.ChoiceField(choices=["RETAIL", "SHNI", "SHARE", "BHNI"])
    lots = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    demat = serializers.UUIDField()
    bank = serializers.UUIDField()
    upi = serializers.UUIDField(allow_null=True, required=False)
    locked = serializers.BooleanField(default=False)


class ValidateRequestSerializer(serializers.Serializer):
    rows = EditedRowSerializer(many=True, max_length=MAX_EDITED_ROWS)
    reserve_ipo_id = serializers.UUIDField(required=False)
    plan_cross_funding_override = serializers.ChoiceField(
        choices=["DEFAULT", "ALLOW", "WARN", "DISALLOW"], default="DEFAULT"
    )


class PlannerValidateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workspace_id):
        workspace = get_object_or_404(
            Workspace.objects.filter(memberships__user=request.user), pk=workspace_id
        )
        serializer = ValidateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            snapshot = build_snapshot(
                workspace=workspace,
                plan_cross_funding_override=serializer.validated_data[
                    "plan_cross_funding_override"
                ],
            )
        except ImproperlyConfigured:
            return Response({"detail": "Planner policy has not been configured."}, status=503)
        try:
            context = quota_context(workspace, snapshot)
            rows, audit = review_quota_rows(snapshot, serializer.validated_data["rows"], context)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        total = audit.planned_total
        issues_by_row = {}
        for issue in audit.issues:
            issues_by_row.setdefault((issue.ipo_id, issue.applicant_id), []).append(issue.code)
        record_beta_event(workspace=workspace, event_type=BetaEvent.Type.PLAN_EDITED)
        return Response(
            {
                "status": "READY" if audit.valid else "BLOCKED",
                "planning_only": snapshot_is_planning_only(snapshot),
                "planned_total": str(total),
                "rows": [
                    {
                        "ipo": row.ipo_id,
                        "applicant": row.applicant_id,
                        "category": row.category,
                        "lots": row.lots,
                        "amount": str(row.amount),
                        "demat": row.demat_id,
                        "bank": row.bank_id,
                        "upi": row.upi_id,
                        "locked": row.locked,
                        "warnings": row.warnings,
                        "blocking_reasons": row_issue_codes(audit.issues, row),
                        "reasons": [],
                    }
                    for row in rows
                ],
                "audit_issues": [asdict(issue) for issue in audit.issues],
                "uncovered": [],
            }
        )


class PlannerRunCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workspace_id):
        workspace = get_object_or_404(
            Workspace.objects.filter(memberships__user=request.user), pk=workspace_id
        )
        if not WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=request.user,
            role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.OPERATOR),
        ).exists():
            return Response(
                {"detail": "Only workspace owners and operators can save plans."}, status=403
            )
        serializer = ValidateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            snapshot = build_snapshot(
                workspace=workspace,
                plan_cross_funding_override=serializer.validated_data[
                    "plan_cross_funding_override"
                ],
            )
            context = quota_context(workspace, snapshot)
            rows, audit = review_quota_rows(snapshot, serializer.validated_data["rows"], context)
            reserve_ipo_id = serializer.validated_data.get("reserve_ipo_id")
            reserved_ipo_ids = None
            if reserve_ipo_id is not None:
                target = str(reserve_ipo_id)
                if target not in {row.ipo_id for row in rows}:
                    raise ValidationError("The IPO to export is not in this plan")
                reserved_ipo_ids = []
                previous = PlanRun.objects.filter(workspace=workspace).first()
                if previous and previous.status == PlanRun.Status.READY:
                    if previous.reserved_ipo_ids is None:
                        reserved_ipo_ids = None
                    else:
                        current_by_ipo = {}
                        for row in rows:
                            current_by_ipo.setdefault(row.ipo_id, []).append(
                                (
                                    row.applicant_id,
                                    row.category,
                                    row.lots,
                                    row.amount,
                                    row.demat_id,
                                    row.bank_id,
                                    row.upi_id,
                                )
                            )
                        for ipo_id in previous.reserved_ipo_ids:
                            if ipo_id not in current_by_ipo:
                                continue
                            if ipo_id == target:
                                continue
                            prior_rows = list(
                                previous.rows.filter(ipo_ref=ipo_id).values_list(
                                    "applicant_ref",
                                    "category",
                                    "lots",
                                    "amount",
                                    "demat_ref",
                                    "bank_ref",
                                    "upi_ref",
                                )
                            )
                            if sorted(prior_rows) != sorted(current_by_ipo[ipo_id]):
                                raise ValidationError(
                                    "An already exported IPO changed. Export that IPO again first."
                                )
                            reserved_ipo_ids.append(ipo_id)
            run = create_reviewed_plan_run(
                workspace=workspace,
                snapshot=snapshot,
                rows=rows,
                audit=audit,
                actor=request.user,
                reserved_ipo_ids=reserved_ipo_ids,
                quota_context=context,
            )
        except ImproperlyConfigured:
            return Response({"detail": "Planner policy has not been configured."}, status=503)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return Response(
            {
                "id": str(run.pk),
                "status": run.status,
                "planning_only": snapshot_is_planning_only(snapshot),
                "planned_total": str(run.planned_total),
                "input_snapshot_hash": run.input_snapshot_hash,
                "output_hash": run.output_hash,
                "audit_issues": run.audit_issues,
                "rows": [
                    {
                        "ipo": row.ipo_id,
                        "applicant": row.applicant_id,
                        "category": row.category,
                        "lots": row.lots,
                        "amount": str(row.amount),
                        "demat": row.demat_id,
                        "bank": row.bank_id,
                        "upi": row.upi_id,
                        "locked": row.locked,
                        "warnings": row.warnings,
                        "blocking_reasons": row_issue_codes(audit.issues, row),
                        "reasons": [asdict(reason) for reason in row.reasons],
                    }
                    for row in rows
                ],
                "uncovered": [],
            },
            status=201,
        )


class WorkspaceCapitalView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = get_object_or_404(
            Workspace.objects.filter(memberships__user=request.user), pk=workspace_id
        )
        balances = {
            str(pk): amount
            for pk, amount in BankAccount.objects.filter(workspace=workspace).values_list(
                "pk", "current_balance"
            )
        }
        latest = PlanRun.objects.filter(workspace=workspace).first()
        planned_by_bank = {}
        applications = list(Application.objects.filter(workspace=workspace))
        tracked_by_row = {item.plan_row_id: item for item in applications}
        active_keys = {
            (
                str(item.ipo_id),
                str(item.applicant_id),
                "SHARE" if item.category == "SHARE" else "PUBLIC",
            )
            for item in applications
            if item.status != Application.Status.CANCELLED
        }
        for item in applications:
            bank_id = str(item.bank_id)
            if item.status in {Application.Status.PLANNED, Application.Status.SUBMITTED}:
                planned_by_bank[bank_id] = planned_by_bank.get(bank_id, 0) + item.amount
        if latest is not None and latest.status != PlanRun.Status.CLEARED:
            for row in latest.rows.all():
                if (
                    latest.reserved_ipo_ids is not None
                    and row.ipo_ref not in latest.reserved_ipo_ids
                ):
                    continue
                if row.pk in tracked_by_row:
                    continue
                if (
                    row.ipo_ref,
                    row.applicant_ref,
                    "SHARE" if row.category == "SHARE" else "PUBLIC",
                ) in active_keys:
                    continue
                planned_by_bank[row.bank_ref] = planned_by_bank.get(row.bank_ref, 0) + row.amount
        blocked_by_bank = {}
        for item in applications:
            if item.status == Application.Status.BLOCKED:
                bank_id = str(item.bank_id)
                blocked_by_bank[bank_id] = blocked_by_bank.get(bank_id, 0) + item.amount
        totals = capital_totals(
            balances, blocked_by_bank=blocked_by_bank, planned_by_bank=planned_by_bank
        )
        by_bank = {}
        for bank_id, balance in balances.items():
            bank_totals = capital_totals(
                {bank_id: balance},
                blocked_by_bank=blocked_by_bank,
                planned_by_bank=planned_by_bank,
            )
            by_bank[bank_id] = {
                "balance": str(bank_totals.balance),
                "blocked": str(bank_totals.blocked),
                "planned": str(bank_totals.planned),
                "available": str(bank_totals.available),
            }
        return Response(
            {
                "balance": str(totals.balance),
                "blocked": str(totals.blocked),
                "planned": str(totals.planned),
                "available": str(totals.available),
                "by_bank": by_bank,
            }
        )


class PlannerLatestRunView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = get_object_or_404(
            Workspace.objects.filter(memberships__user=request.user), pk=workspace_id
        )
        latest = PlanRun.objects.filter(workspace=workspace).first()
        return Response(
            {
                "id": str(latest.pk) if latest else None,
                "status": latest.status if latest else None,
                "planned_total": str(latest.planned_total) if latest else "0.00",
            }
        )


class PlannerRunClearView(APIView):
    permission_classes = [WorkspaceDataPermission]

    def post(self, request, workspace_id, run_id):
        run = get_object_or_404(PlanRun.objects.filter(workspace_id=workspace_id), pk=run_id)
        try:
            clear_plan_run(plan_run=run, actor=request.user)
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=409)
        return Response({"id": str(run.pk), "status": PlanRun.Status.CLEARED})
