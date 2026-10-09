import re

from django.db import IntegrityError, transaction
from rest_framework import serializers

from investors.models import DematAccount, Investor, pan_hash_for_workspace

PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


class InvestorSerializer(serializers.ModelSerializer):
    pan = serializers.CharField(write_only=True, required=False)
    pan_masked = serializers.CharField(read_only=True)

    class Meta:
        model = Investor
        fields = (
            "id",
            "name",
            "pan",
            "pan_masked",
            "planning_priority",
            "active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "pan_masked", "created_at", "updated_at")

    def validate_pan(self, value):
        normalized = value.strip().upper()
        if not PAN_PATTERN.fullmatch(normalized):
            raise serializers.ValidationError("Enter a valid PAN.")
        return normalized

    def validate(self, attrs):
        if self.instance is None and "pan" not in attrs:
            raise serializers.ValidationError({"pan": "PAN is required."})
        if "pan" in attrs:
            workspace = self.context["workspace"]
            existing = Investor.objects.filter(
                workspace=workspace,
                pan_lookup_hash=pan_hash_for_workspace(workspace.pk, attrs["pan"]),
            )
            if self.instance is not None:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError({"pan": "This PAN is already in this workspace."})
        return attrs

    def create(self, validated_data):
        pan = validated_data.pop("pan")
        investor = Investor(workspace=self.context["workspace"], **validated_data)
        investor.set_pan(pan)
        try:
            with transaction.atomic():
                investor.save()
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {"pan": "This PAN is already in this workspace."}
            ) from exc
        return investor

    def update(self, instance, validated_data):
        pan = validated_data.pop("pan", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if pan is not None:
            instance.set_pan(pan)
        try:
            with transaction.atomic():
                instance.save()
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {"pan": "This PAN is already in this workspace."}
            ) from exc
        return instance


class DematAccountSerializer(serializers.ModelSerializer):
    dp_id = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=32)
    client_id = serializers.CharField(write_only=True, required=False, max_length=32)
    dp_id_masked = serializers.CharField(read_only=True)
    client_id_masked = serializers.CharField(read_only=True)

    class Meta:
        model = DematAccount
        fields = (
            "id",
            "depository",
            "dp_id",
            "dp_id_masked",
            "client_id",
            "client_id_masked",
            "broker",
            "active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "dp_id_masked", "client_id_masked", "created_at", "updated_at")

    def validate(self, attrs):
        if self.instance is None:
            depository = attrs.get("depository")
            missing = {}
            if "client_id" not in attrs:
                missing["client_id"] = "This field is required."
            if depository == DematAccount.Depository.NSDL and not attrs.get("dp_id"):
                missing["dp_id"] = "This field is required for NSDL accounts."
            if missing:
                raise serializers.ValidationError(missing)
        return attrs

    def create(self, validated_data):
        dp_id = validated_data.pop("dp_id", "")
        client_id = validated_data.pop("client_id")
        demat = DematAccount(investor=self.context["investor"], **validated_data)
        demat.set_dp_id(dp_id)
        demat.set_client_id(client_id)
        demat.save()
        return demat

    def update(self, instance, validated_data):
        dp_id = validated_data.pop("dp_id", None)
        client_id = validated_data.pop("client_id", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if dp_id is not None:
            instance.set_dp_id(dp_id)
        if client_id is not None:
            instance.set_client_id(client_id)
        instance.save()
        return instance
