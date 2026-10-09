from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ipos.bse_feed import current_bse_issues
from ipos.feed_watch import current_feed_issues
from ipos.gmp_effective import resolve_gmp
from ipos.gmp_policy import current_gmp_policy
from ipos.models import GMPObservation, GMPProviderState, SEBIFiling
from ipos.overrides import published_ipos
from ipos.public_serializers import GMPHistorySerializer, PublicIPOSerializer


class PublicIPOViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PublicIPOSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return published_ipos().order_by("open_date", "id")


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
