from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Workspace
from accounts.permissions import WorkspaceDataPermission
from core.audit import record_event
from ipos.gmp_effective import resolve_gmp
from ipos.gmp_policy import current_gmp_policy
from ipos.models import IPOUserDecision
from ipos.overrides import effective_ipo_values, published_ipos
from ipos.public_serializers import gmp_percent
from ipos.selection import has_open_auto_ipo, select_ipo, selection_status


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
        ipos = list(published_ipos().order_by("open_date", "id"))
        effective_values = {ipo.pk: effective_ipo_values(ipo) for ipo in ipos}
        now = timezone.now()
        freshness_hours = current_gmp_policy().freshness_hours
        issue_types = tuple(workspace.auto_select_issue_types or ["MAINBOARD"])
        has_open = has_open_auto_ipo(
            list(effective_values.values()), issue_types=issue_types, at=now
        )
        for ipo in ipos:
            resolution = resolve_gmp(ipo, at=now)
            latest = resolution.effective
            effective = effective_values[ipo.pk]
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
                issue_type=effective["issue_type"],
                auto_issue_types=issue_types,
                status=selection_status(effective, at=now),
                allow_upcoming=not has_open,
                has_stale_gmp=bool(resolution.stale_source_keys),
            )
            rows.append(
                {
                    "ipo": str(ipo.pk),
                    "decision": decision,
                    "mode": mode,
                    "selected": selected,
                    "reason": reason,
                    "gmp_freshness_hours": freshness_hours,
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
        now = timezone.now()
        resolution = resolve_gmp(ipo, at=now)
        latest = resolution.effective
        effective = effective_ipo_values(ipo)
        upper = effective["upper_price"]
        current_percent = gmp_percent(latest.value_per_share, upper) if latest else None
        issue_types = tuple(workspace.auto_select_issue_types or ["MAINBOARD"])
        has_open = has_open_auto_ipo(
            [effective_ipo_values(item) for item in published_ipos()],
            issue_types=issue_types,
            at=now,
        )
        selected, reason = select_ipo(
            decision=decision.decision,
            gmp_percent=current_percent,
            threshold=workspace.auto_select_gmp_percent,
            issue_type=effective["issue_type"],
            auto_issue_types=issue_types,
            status=selection_status(effective, at=now),
            allow_upcoming=not has_open,
            has_stale_gmp=bool(resolution.stale_source_keys),
        )
        return Response(
            {
                "ipo": str(ipo.pk),
                "decision": decision.decision,
                "mode": decision.mode,
                "selected": selected,
                "reason": reason,
                "gmp_freshness_hours": current_gmp_policy().freshness_hours,
            }
        )
