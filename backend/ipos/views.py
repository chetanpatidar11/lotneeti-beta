from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets

from core.audit import record_event
from ipos.models import IPO, GMPObservation
from ipos.serializers import ManualGMPSerializer, ManualIPOSerializer
from platform_admin.permissions import IsFounderAdmin


class ManualIPOViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ManualIPOSerializer
    permission_classes = [IsFounderAdmin]

    def get_queryset(self):
        return IPO.objects.filter(source_key="manual").order_by("open_date", "id")

    def perform_create(self, serializer):
        with transaction.atomic():
            ipo = serializer.save()
            record_event(action="ipo.manual_created", target=ipo, actor=self.request.user)

    def perform_update(self, serializer):
        with transaction.atomic():
            ipo = serializer.save()
            record_event(
                action="ipo.manual_updated",
                target=ipo,
                actor=self.request.user,
                metadata={"fields": sorted(serializer.validated_data)},
            )


class ManualGMPViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ManualGMPSerializer
    permission_classes = [IsFounderAdmin]

    def get_ipo(self):
        return get_object_or_404(IPO, pk=self.kwargs["ipo_id"])

    def get_queryset(self):
        return GMPObservation.objects.filter(ipo=self.get_ipo())

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "ipo": self.get_ipo()}

    def perform_create(self, serializer):
        with transaction.atomic():
            observation = serializer.save()
            record_event(
                action="gmp.manual_recorded",
                target=observation,
                actor=self.request.user,
                metadata={"ipo_id": str(observation.ipo_id)},
            )
