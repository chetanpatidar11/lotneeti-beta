from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework import serializers

from ipos.content import published_summary
from ipos.gmp_effective import effective_observation_value, resolve_gmp
from ipos.models import IPO, GMPObservation
from ipos.overrides import OVERRIDABLE_FIELDS, effective_ipo_resolution, effective_ipo_values


def gmp_percent(value: Decimal, upper_price: Decimal) -> Decimal:
    return (value * Decimal("100") / upper_price).quantize(Decimal("0.01"))


class GMPHistorySerializer(serializers.ModelSerializer):
    percent = serializers.SerializerMethodField()
    source_value_per_share = serializers.CharField(source="value_per_share", read_only=True)
    enabled = serializers.SerializerMethodField()
    fresh = serializers.SerializerMethodField()
    included_in_consensus = serializers.SerializerMethodField()

    class Meta:
        model = GMPObservation
        fields = (
            "id",
            "value_per_share",
            "source_value_per_share",
            "percent",
            "observed_at",
            "fetched_at",
            "source_key",
            "source_url",
            "enabled",
            "fresh",
            "included_in_consensus",
        )

    def get_percent(self, obj):
        value = effective_observation_value(obj)
        return str(gmp_percent(value, effective_ipo_values(obj.ipo)["upper_price"]))

    def to_representation(self, instance):
        result = super().to_representation(instance)
        result["value_per_share"] = str(effective_observation_value(instance))
        return result

    def get_enabled(self, obj):
        return self.context.get("states", {}).get(obj.source_key, True)

    def get_fresh(self, obj):
        age = self.context["now"] - obj.observed_at
        return timedelta(0) <= age < timedelta(hours=self.context["freshness_hours"])

    def get_included_in_consensus(self, obj):
        return obj.pk in self.context.get("fresh_ids", set())


class PublicIPOSerializer(serializers.ModelSerializer):
    current_gmp = serializers.SerializerMethodField()
    current_gmp_percent = serializers.SerializerMethodField()
    current_gmp_observed_at = serializers.SerializerMethodField()
    gmp_source_count = serializers.SerializerMethodField()
    gmp_minimum = serializers.SerializerMethodField()
    gmp_maximum = serializers.SerializerMethodField()
    gmp_median = serializers.SerializerMethodField()
    gmp_latest_observed_at = serializers.SerializerMethodField()
    gmp_source_conflict = serializers.SerializerMethodField()
    gmp_stale_source_count = serializers.SerializerMethodField()
    gmp_data_state = serializers.SerializerMethodField()
    gmp_has_founder_correction = serializers.SerializerMethodField()
    company_summary = serializers.SerializerMethodField()
    financial_summary = serializers.SerializerMethodField()
    risk_summary = serializers.SerializerMethodField()

    class Meta:
        model = IPO
        fields = (
            "id",
            "issuer_name",
            "symbol",
            "issue_type",
            "source_market",
            "listing_exchanges",
            "designated_exchange",
            "lower_price",
            "upper_price",
            "lot_size",
            "open_date",
            "close_date",
            "allotment_date",
            "listing_date",
            "status",
            "current_gmp",
            "current_gmp_percent",
            "current_gmp_observed_at",
            "gmp_source_count",
            "gmp_minimum",
            "gmp_maximum",
            "gmp_median",
            "gmp_latest_observed_at",
            "gmp_source_conflict",
            "gmp_stale_source_count",
            "gmp_data_state",
            "gmp_has_founder_correction",
            "company_summary",
            "financial_summary",
            "risk_summary",
        )

    def get_company_summary(self, obj):
        return published_summary(obj, "COMPANY")

    def get_financial_summary(self, obj):
        return published_summary(obj, "FINANCIAL")

    def get_risk_summary(self, obj):
        return published_summary(obj, "RISK")

    def to_representation(self, instance):
        result = super().to_representation(instance)
        effective = self._ipo_resolution(instance).values
        for name in OVERRIDABLE_FIELDS.intersection(result):
            result[name] = self.fields[name].to_representation(effective[name])
        close_at = datetime.combine(
            effective["close_date"], time(17), tzinfo=ZoneInfo("Asia/Kolkata")
        )
        if effective["status"] == IPO.Status.OPEN and timezone.now() >= close_at:
            result["status"] = IPO.Status.CLOSED
        return result

    def _ipo_resolution(self, obj):
        if not hasattr(obj, "_ipo_resolution"):
            obj._ipo_resolution = effective_ipo_resolution(obj)
        return obj._ipo_resolution

    def _resolution(self, obj):
        if not hasattr(obj, "_gmp_resolution"):
            obj._gmp_resolution = resolve_gmp(obj)
        return obj._gmp_resolution

    def _latest(self, obj):
        return self._resolution(obj).effective

    def get_current_gmp(self, obj):
        latest = self._latest(obj)
        return str(latest.value_per_share) if latest else None

    def get_current_gmp_percent(self, obj):
        latest = self._latest(obj)
        upper = effective_ipo_values(obj)["upper_price"]
        return str(gmp_percent(latest.value_per_share, upper)) if latest else None

    def get_current_gmp_observed_at(self, obj):
        latest = self._latest(obj)
        return latest.observed_at.isoformat() if latest else None

    def get_gmp_source_count(self, obj):
        return self._resolution(obj).source_count

    def get_gmp_minimum(self, obj):
        value = self._resolution(obj).minimum
        return str(value) if value is not None else None

    def get_gmp_maximum(self, obj):
        value = self._resolution(obj).maximum
        return str(value) if value is not None else None

    def get_gmp_median(self, obj):
        value = self._resolution(obj).median
        return str(value) if value is not None else None

    def get_gmp_latest_observed_at(self, obj):
        value = self._resolution(obj).latest_observed_at
        return value.isoformat() if value is not None else None

    def get_gmp_source_conflict(self, obj):
        return self._resolution(obj).source_conflict

    def get_gmp_stale_source_count(self, obj):
        return len(self._resolution(obj).stale_source_keys)

    def get_gmp_data_state(self, obj):
        resolution = self._resolution(obj)
        return (
            "FRESH"
            if resolution.effective
            else "STALE"
            if resolution.stale_source_keys
            else "MISSING"
        )

    def get_gmp_has_founder_correction(self, obj):
        latest = self._latest(obj)
        return latest.corrected if latest else False
