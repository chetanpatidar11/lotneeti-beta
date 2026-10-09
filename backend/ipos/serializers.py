from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from ipos.models import IPO, GMPObservation
from ipos.providers import ManualGMPProvider, ManualIPOProvider


class ManualIPOSerializer(serializers.ModelSerializer):
    class Meta:
        model = IPO
        fields = (
            "id",
            "issuer_name",
            "symbol",
            "issue_type",
            "lower_price",
            "upper_price",
            "lot_size",
            "open_date",
            "close_date",
            "allotment_date",
            "listing_date",
            "status",
            "publication_state",
            "source_key",
            "source_record_id",
            "source_url",
            "source_observed_at",
            "source_payload_hash",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "source_key",
            "source_record_id",
            "source_observed_at",
            "source_payload_hash",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        values = {field: getattr(self.instance, field) for field in attrs} if self.instance else {}
        values.update(attrs)
        for field, message in (
            ("upper_price", "Upper price must be at least the lower price."),
            ("close_date", "Closing date cannot be before opening date."),
            ("allotment_date", "Allotment date cannot be before closing date."),
            ("listing_date", "Listing date cannot be before allotment date."),
        ):
            left_field = {
                "upper_price": "lower_price",
                "close_date": "open_date",
                "allotment_date": "close_date",
                "listing_date": "allotment_date",
            }[field]
            left = values.get(left_field, getattr(self.instance, left_field, None))
            right = values.get(field, getattr(self.instance, field, None))
            if left is not None and right is not None and left > right:
                raise serializers.ValidationError({field: message})
        return attrs

    def create(self, validated_data):
        try:
            return ManualIPOProvider().create(validated_data)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error

    def update(self, instance, validated_data):
        try:
            return ManualIPOProvider().update(instance, validated_data)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error


class ManualGMPSerializer(serializers.ModelSerializer):
    class Meta:
        model = GMPObservation
        fields = (
            "id",
            "value_per_share",
            "observed_at",
            "fetched_at",
            "source_key",
            "source_record_id",
            "source_url",
            "source_payload_hash",
        )
        read_only_fields = (
            "id",
            "fetched_at",
            "source_key",
            "source_record_id",
            "source_payload_hash",
        )

    def create(self, validated_data):
        try:
            return ManualGMPProvider().record(
                ipo=self.context["ipo"],
                recorded_by=self.context["request"].user,
                **validated_data,
            )
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error
