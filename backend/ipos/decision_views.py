from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Workspace
from accounts.permissions import WorkspaceDataPermission
from core.audit import record_event
from ipos.gmp_effective import latest_effective_gmp
from ipos.models import IPOUserDecision
from ipos.overrides import effective_ipo_values, published_ipos
from ipos.public_serializers import gmp_percent
from ipos.selection import select_ipo


class ManualDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["DEFAULT", "APPLY", "SKIP"], required=False)
    mode = serializers.ChoiceField(choices=IPOUserDecision.Mode.choices, required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("A decision or mode is required.")
        return attrs


class WorkspaceIPOListView(APIView):
    permission_classes = [WorkspaceDataPermission]

    def get(self, request, workspace_id):
        workspace = get_object_or_404(
            Workspace.objects.filter(memberships__user=request.user), pk=workspace_id
        )
        decisions = {
            item.ipo_id: item for item in IPOUserDecision.objects.filter(workspace=workspace)
        }
        rows = []
        ipos = published_ipos().order_by("open_date", "id")
        for ipo in ipos:
            latest = latest_effective_gmp(ipo)
            effective = effective_ipo_values(ipo)
            current_percent = (
                gmp_percent(latest.value_per_share, effective["upper_price"]) if latest else None
            )
            stored = decisions.get(ipo.pk)
            decision = stored.decision if stored else IPOUserDecision.Decision.DEFAULT
            mode = stored.mode if stored else IPOUserDecision.Mode.RETAIL_ONLY
            selected, reason = select_ipo(
                decision=decision,
                gmp_percent=current_percent,
                threshold=workspace.auto_select_gmp_percent,
            )
            rows.append(
                {
                    "ipo": str(ipo.pk),
                    "decision": decision,
                    "mode": mode,
                    "selected": selected,
                    "reason": reason,
                }
            )
        return Response(rows)


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
        latest = latest_effective_gmp(ipo)
        upper = effective_ipo_values(ipo)["upper_price"]
        current_percent = gmp_percent(latest.value_per_share, upper) if latest else None
        selected, reason = select_ipo(
            decision=decision.decision,
            gmp_percent=current_percent,
            threshold=workspace.auto_select_gmp_percent,
        )
        return Response(
            {
                "ipo": str(ipo.pk),
                "decision": decision.decision,
                "mode": decision.mode,
                "selected": selected,
                "reason": reason,
            }
        )
