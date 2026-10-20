from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Workspace
from accounts.permissions import WorkspaceDataPermission
from core.audit import record_event
from ipos.gmp_effective import latest_selection_gmp
from ipos.models import IPOUserDecision
from ipos.overrides import effective_ipo_values, published_ipos
from ipos.public_serializers import gmp_percent
from ipos.selection import resolve_ipo_choices


class ManualDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["DEFAULT", "APPLY", "SKIP"], required=False)
    mode = serializers.ChoiceField(choices=IPOUserDecision.Mode.choices, required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("A decision or mode is required.")
        return attrs


def workspace_selection_rows(workspace, *, at):
    decisions = {item.ipo_id: item for item in IPOUserDecision.objects.filter(workspace=workspace)}
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
        with transaction.atomic():
            decision, _ = IPOUserDecision.objects.get_or_create(
                workspace=workspace,
                ipo=ipo,
            )
            for field, value in serializer.validated_data.items():
                setattr(decision, field, value)
            decision.updated_by = request.user
            decision.save()
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
