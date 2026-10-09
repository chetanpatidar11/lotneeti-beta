from dataclasses import asdict, replace

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Workspace, WorkspaceMembership
from applications.models import Application
from core.beta_events import record_beta_event
from core.models import BetaEvent
from funding.models import BankAccount
from planner.capital import capital_totals
from planner.dto import LockedRowInput
from planner.engine import generate_proposal
from planner.manual_plan import review_manual_rows
from planner.models import PlanRun
from planner.persistence import create_reviewed_plan_run
from planner.snapshot_builder import build_snapshot


class LockedRowSerializer(serializers.Serializer):
    ipo = serializers.UUIDField()
    applicant = serializers.UUIDField()
    category = serializers.ChoiceField(choices=["RETAIL", "SHNI"])
    lots = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    demat = serializers.UUIDField()
    bank = serializers.UUIDField()
    upi = serializers.UUIDField()


class PreviewRequestSerializer(serializers.Serializer):
    ipo_ids = serializers.ListField(child=serializers.UUIDField(), required=False, allow_empty=True)
    locked_rows = LockedRowSerializer(many=True, required=False)
    plan_cross_funding_override = serializers.ChoiceField(
        choices=["DEFAULT", "ALLOW", "WARN", "DISALLOW"], default="DEFAULT"
    )


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
            if any(str(item[field]) not in ids for field, ids in known.items()):
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
                    upi_id=str(item["upi"]),
                )
            )
        snapshot = replace(snapshot, locked_rows=tuple(locks))
        proposal = generate_proposal(snapshot)
        record_beta_event(workspace=workspace, event_type=BetaEvent.Type.PLAN_GENERATED)
        return Response(
            {
                "planner_version": proposal.planner_version,
                "settings_version": proposal.settings_version,
                "input_snapshot_hash": proposal.input_snapshot_hash,
                "output_hash": proposal.output_hash,
                "status": "READY" if proposal.audit.valid else "BLOCKED",
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


class EditedRowSerializer(serializers.Serializer):
    ipo = serializers.UUIDField()
    applicant = serializers.UUIDField()
    category = serializers.ChoiceField(choices=["RETAIL", "SHNI"])
    lots = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    demat = serializers.UUIDField()
    bank = serializers.UUIDField()
    upi = serializers.UUIDField()
    locked = serializers.BooleanField(default=False)


class ValidateRequestSerializer(serializers.Serializer):
    rows = EditedRowSerializer(many=True)
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
            rows, audit = review_manual_rows(snapshot, serializer.validated_data["rows"])
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
                        "blocking_reasons": issues_by_row.get((row.ipo_id, row.applicant_id), []),
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
            rows, audit = review_manual_rows(snapshot, serializer.validated_data["rows"])
            run = create_reviewed_plan_run(
                workspace=workspace, snapshot=snapshot, rows=rows, audit=audit, actor=request.user
            )
        except ImproperlyConfigured:
            return Response({"detail": "Planner policy has not been configured."}, status=503)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return Response(
            {
                "id": str(run.pk),
                "status": run.status,
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
                        "blocking_reasons": [
                            issue.code
                            for issue in audit.issues
                            if issue.ipo_id == row.ipo_id and issue.applicant_id == row.applicant_id
                        ],
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
        applications = {
            (str(item.ipo_id), str(item.applicant_id)): item
            for item in Application.objects.filter(workspace=workspace)
        }
        if latest is not None:
            for row in latest.rows.all():
                tracked = applications.get((row.ipo_ref, row.applicant_ref))
                if tracked is not None and tracked.status not in {
                    Application.Status.PLANNED,
                    Application.Status.SUBMITTED,
                }:
                    continue
                planned_by_bank[row.bank_ref] = planned_by_bank.get(row.bank_ref, 0) + row.amount
        blocked_by_bank = {}
        for item in applications.values():
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
