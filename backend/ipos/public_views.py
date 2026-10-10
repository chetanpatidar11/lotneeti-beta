from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ipos.bse_feed import current_bse_issues
from ipos.feed_watch import current_feed_issues
from ipos.gmp_effective import resolve_gmp
from ipos.gmp_policy import current_gmp_policy
from ipos.models import GMPObservation, GMPProviderState, IPOProviderSyncState, SEBIFiling
from ipos.overrides import published_ipos
from ipos.public_serializers import GMPHistorySerializer, PublicIPOSerializer
from ipos.tasks import run_ipo_sync
from platform_admin.permissions import IsFounderAdmin


class PublicIPOViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PublicIPOSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return published_ipos().order_by("open_date", "id")


class MarketPreviewView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        # Only market facts enter this anonymous response; workspace data stays private.
        ipos = list(
            published_ipos().filter(source_key="investorgain").order_by("-open_date", "id")[:24]
        )
        rows = []
        for ipo in ipos:
            item = PublicIPOSerializer(ipo).data
            rows.append(
                {
                    key: item[key]
                    for key in (
                        "issuer_name",
                        "issue_type",
                        "lower_price",
                        "upper_price",
                        "lot_size",
                        "open_date",
                        "close_date",
                        "allotment_date",
                        "status",
                        "current_gmp",
                        "current_gmp_percent",
                    )
                }
            )
        state = IPOProviderSyncState.objects.filter(source_key="investorgain").first()
        return Response(
            {
                "issues": rows,
                "last_success_at": state.last_success_at if state else None,
                "status": state.last_status if state else "NEVER",
            }
        )


class InvestorGainSyncView(APIView):
    permission_classes = [IsAuthenticated]

    def _status(self, request):
        state = IPOProviderSyncState.objects.filter(source_key="investorgain").first()
        return {
            "provider": "InvestorGain",
            "founder": bool(request.user.is_staff and request.user.is_founder_admin),
            "can_sync": IsFounderAdmin().has_permission(request, self),
            "last_attempt_at": state.last_attempt_at if state else None,
            "last_success_at": state.last_success_at if state else None,
            "status": state.last_status if state else "NEVER",
        }

    def get(self, request):
        return Response(self._status(request))

    def post(self, request):
        if not IsFounderAdmin().has_permission(request, self):
            raise PermissionDenied("Founder verification is required to refresh market data.")
        # One operator click can spend one licensed request; coalesce repeats.
        if not cache.add("ipo-sync:investorgain-manual-cooldown", "running", timeout=300):
            return Response({**self._status(request), "result": "RATE_LIMITED"}, status=429)
        result = run_ipo_sync(provider="investorgain", manual=True)["investorgain"]
        if result.get("status") != "OK":
            cache.delete("ipo-sync:investorgain-manual-cooldown")
        return Response(
            {**self._status(request), "result": result},
            status=429 if result.get("status") == "RATE_LIMITED" else 200,
        )


class IPOFeedWatchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        nse = current_feed_issues()
        known = {item["symbol"] for item in nse}
        bse_only = [item for item in current_bse_issues() if item["symbol"] not in known]
        return Response(nse + bse_only)


class SEBIFilingWatchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            [
                {
                    "issuer_name": item.issuer_name,
                    "document_type": item.document_type,
                    "document_url": item.document_url or item.source_url,
                    "filing_date": item.filing_date.isoformat(),
                }
                for item in SEBIFiling.objects.all()[:25]
            ]
        )


class GMPHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, ipo_id):
        ipo = get_object_or_404(published_ipos(), pk=ipo_id)
        now = timezone.now()
        resolution = resolve_gmp(ipo, at=now)
        policy = current_gmp_policy()
        observations = GMPObservation.objects.filter(ipo=ipo).select_related("ipo")
        states = dict(GMPProviderState.objects.values_list("provider_key", "enabled"))
        return Response(
            GMPHistorySerializer(
                observations,
                many=True,
                context={
                    "states": states,
                    "fresh_ids": {item.pk for item in resolution.fresh_observations},
                    "now": now,
                    "freshness_hours": policy.freshness_hours,
                },
            ).data
        )
