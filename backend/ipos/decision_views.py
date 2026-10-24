from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Workspace
from accounts.permissions import WorkspaceDataPermission
from core.audit import record_event
from investors.models import Investor
from ipos.gmp_effective import latest_selection_gmp
from ipos.models import IPOUserDecision
from ipos.overrides import effective_ipo_values, published_ipos
from ipos.public_serializers import gmp_percent
from ipos.quota_terms import confirmed_shareholder_quota, shareholder_terms_fingerprint
from ipos.selection import resolve_ipo_choices


class OmissibleBooleanField(serializers.BooleanField):
    default_empty_html = serializers.empty


class ManualDecisionSerializer(serializers.Serializer):
    shareholder_preferred = OmissibleBooleanField(required=False)
    shareholder_eligible = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=1000
    )
    decision = serializers.ChoiceField(choices=["DEFAULT", "APPLY", "SKIP"], required=False)
    mode = serializers.ChoiceField(choices=IPOUserDecision.Mode.choices, required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("A decision or mode is required.")
        return attrs


def workspace_selection_rows(workspace, *, at):
    decisions = {
        item.ipo_id: item
        for item in IPOUserDecision.objects.filter(workspace=workspace).prefetch_related(
            "shareholder_eligible"
        )
    }
    ipos = list(published_ipos().order_by("open_date", "id"))
    effective_values = {ipo.pk: effective_ipo_values(ipo) for ipo in ipos}
    candidates = []
    for ipo in ipos:
        latest = latest_selection_gmp(ipo, at=at)
        effective = effective_values[ipo.pk]
        current_percent = (
            gmp_percent(latest.value_per_share, effective["upper_price"]) if latest else None
        )
        stored = decisions.get(ipo.pk)
        decision = stored.decision if stored else IPOUserDecision.Decision.DEFAULT
        candidates.append((str(ipo.pk), effective, decision, current_percent))
    choices = resolve_ipo_choices(
        candidates=candidates,
        threshold=workspace.auto_select_gmp_percent,
        enabled=workspace.auto_select_enabled,
        issue_types=tuple(workspace.auto_select_issue_types or ["MAINBOARD"]),
        at=at,
    )
    return [
        {
            "ipo": str(ipo.pk),
            "decision": decisions[ipo.pk].decision
            if ipo.pk in decisions
            else IPOUserDecision.Decision.DEFAULT,
            "mode": decisions[ipo.pk].mode
            if ipo.pk in decisions
            else IPOUserDecision.Mode.RETAIL_ONLY,
            "shareholder_terms_changed": bool(
                ipo.pk in decisions
                and ipo.shareholder_quota
                and decisions[ipo.pk].shareholder_preferred
                and decisions[ipo.pk].shareholder_terms_fingerprint
                != shareholder_terms_fingerprint(ipo)
            ),
            "shareholder_preferred": decisions[ipo.pk].shareholder_preferred
            if ipo.pk in decisions
            else False,
            "shareholder_eligible": [
                str(item.pk)
                for item in decisions[ipo.pk].shareholder_eligible.all()
                if decisions[ipo.pk].shareholder_terms_fingerprint
                == shareholder_terms_fingerprint(ipo)
            ]
            if ipo.pk in decisions
            else [],
            "selected": choices[str(ipo.pk)][0],
            "reason": choices[str(ipo.pk)][1],
        }
        for ipo in ipos
    ]


class WorkspaceIPOListView(APIView):
    permission_classes = [WorkspaceDataPermission]

    def get(self, request, workspace_id):
        workspace = get_object_or_404(
            Workspace.objects.filter(memberships__user=request.user), pk=workspace_id
        )
        return Response(workspace_selection_rows(workspace, at=timezone.now()))


class WorkspaceIPODecisionView(APIView):
    permission_classes = [WorkspaceDataPermission]

    def patch(self, request, workspace_id, ipo_id):
        workspace = get_object_or_404(
            Workspace.objects.filter(memberships__user=request.user), pk=workspace_id
        )
        ipo = get_object_or_404(published_ipos(), pk=ipo_id)
        serializer = ManualDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        eligible_ids = values.get("shareholder_eligible")
        if values.get("shareholder_preferred") or eligible_ids:
            if not confirmed_shareholder_quota(ipo):
                raise serializers.ValidationError("This IPO has no confirmed shareholder quota.")
            if eligible_ids is not None and len(set(eligible_ids)) != len(eligible_ids):
                raise serializers.ValidationError("Choose each eligible investor only once.")
            if eligible_ids is not None and Investor.objects.filter(
                pk__in=eligible_ids, workspace=workspace, active=True, is_deleted=False
            ).count() != len(eligible_ids):
                raise serializers.ValidationError("Choose active investors in this account.")
        with transaction.atomic():
            decision, _ = IPOUserDecision.objects.get_or_create(
                workspace=workspace,
                ipo=ipo,
            )
            for field, value in values.items():
                if field != "shareholder_eligible":
                    setattr(decision, field, value)
            if values.get("shareholder_preferred", decision.shareholder_preferred) and not (
                eligible_ids if eligible_ids is not None else decision.shareholder_eligible.exists()
            ):
                raise serializers.ValidationError(
                    "Select at least one shareholder-eligible investor."
                )
            if eligible_ids is not None:
                decision.shareholder_terms_fingerprint = shareholder_terms_fingerprint(ipo)
            decision.updated_by = request.user
            decision.save()
            if eligible_ids is not None:
                decision.shareholder_eligible.set(eligible_ids)
            record_event(
                action="ipo.decision_updated",
                target=decision,
                actor=request.user,
                workspace=workspace,
                metadata={
                    "ipo_id": str(ipo.pk),
                    "decision": decision.decision,
                    "mode": decision.mode,
                },
            )
        rows = workspace_selection_rows(workspace, at=timezone.now())
        return Response(next(row for row in rows if row["ipo"] == str(ipo.pk)))
