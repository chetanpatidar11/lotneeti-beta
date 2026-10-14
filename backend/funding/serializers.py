import re
from decimal import Decimal

from rest_framework import serializers

from core.crypto import decrypt_value
from funding.models import (
    BalanceChange,
    BankAccount,
    FundingPreference,
    RecurringDebit,
    UPIHandle,
    account_hash_for_workspace,
    upi_hash_for_workspace,
)
from investors.models import Investor


class BankAccountSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(queryset=Investor.objects.none())
    restricted_investor = serializers.PrimaryKeyRelatedField(
        queryset=Investor.objects.none(), required=False, allow_null=True
    )
    account_number = serializers.CharField(write_only=True, required=False, max_length=40)
    account_masked = serializers.CharField(read_only=True)
    initial_balance = serializers.DecimalField(
        max_digits=14, decimal_places=2, write_only=True, required=False, default=Decimal("0.00")
    )

    class Meta:
        model = BankAccount
        fields = (
            "id",
            "owner",
            "bank_name",
            "account_number",
            "account_masked",
            "is_placeholder",
            "initial_balance",
            "current_balance",
            "cross_funding_policy",
            "restricted_investor",
            "active",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "account_masked",
            "is_placeholder",
            "current_balance",
            "created_at",
            "updated_at",
        )

    def get_fields(self):
        fields = super().get_fields()
        workspace = self.context.get("workspace")
        if workspace is not None:
            scoped_investors = Investor.objects.filter(workspace=workspace)
            fields["owner"].queryset = scoped_investors
            fields["restricted_investor"].queryset = scoped_investors
        return fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if self.context.get("reveal_details"):
            data["account_number"] = decrypt_value(
                instance.account_ciphertext, purpose="bank-account"
            )
        return data

    def validate(self, attrs):
        if self.instance is None and "account_number" not in attrs:
            raise serializers.ValidationError({"account_number": "Account number is required."})
        owner = attrs.get("owner", getattr(self.instance, "owner", None))
        effective_active = attrs.get("active", self.instance.active if self.instance else True)
        if effective_active and owner is not None and not owner.active:
            raise serializers.ValidationError({"owner": "Activate the bank account owner first."})
        if self.instance is not None and "initial_balance" in self.initial_data:
            raise serializers.ValidationError(
                {"initial_balance": "Use a balance action to change this amount."}
            )
        if self.instance is not None and self.instance.is_placeholder:
            has_real_details = bool(attrs.get("bank_name")) and bool(attrs.get("account_number"))
            if has_real_details and "owner" not in attrs:
                raise serializers.ValidationError(
                    {"owner": "Choose the holder of this bank and UPI ID."}
                )
            if attrs.get("active") and not has_real_details:
                raise serializers.ValidationError(
                    {"active": "Enter the real bank name and account number before activating."}
                )
        if "account_number" in attrs:
            number = attrs["account_number"].strip()
            if not number:
                raise serializers.ValidationError({"account_number": "Account number is required."})
            attrs["account_number"] = number
            if (
                self.instance is not None
                and self.instance.is_placeholder
                and (
                    account_hash_for_workspace(self.context["workspace"].pk, number)
                    == self.instance.account_lookup_hash
                )
            ):
                raise serializers.ValidationError(
                    {"account_number": "Enter the real account number, not the UPI reference."}
                )
            existing = BankAccount.objects.filter(
                workspace=self.context["workspace"],
                account_lookup_hash=account_hash_for_workspace(
                    self.context["workspace"].pk, number
                ),
            )
            if self.instance is not None:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError(
                    {"account_number": "This account is already in this workspace."}
                )
        return attrs

    def create(self, validated_data):
        number = validated_data.pop("account_number")
        balance = validated_data.pop("initial_balance", Decimal("0.00"))
        bank = BankAccount(
            workspace=self.context["workspace"], current_balance=balance, **validated_data
        )
        bank.set_account_number(number)
        bank.save()
        BalanceChange.objects.create(
            bank=bank,
            operation=BalanceChange.Operation.SET,
            old_balance=Decimal("0.00"),
            delta=balance,
            new_balance=balance,
            actor=self.context["request"].user,
            note="Opening balance",
        )
        return bank

    def update(self, instance, validated_data):
        number = validated_data.pop("account_number", None)
        validated_data.pop("initial_balance", None)
        was_placeholder = instance.is_placeholder
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if number is not None:
            instance.set_account_number(number)
        if instance.is_placeholder and number is not None and instance.bank_name:
            instance.is_placeholder = False
        instance.save()
        if was_placeholder and not instance.is_placeholder:
            instance.upis.update(holder=instance.owner)
        return instance


UPI_PATTERN = re.compile(r"^[a-z0-9._-]+@[a-z0-9._-]+$")


class UPIHandleSerializer(serializers.ModelSerializer):
    holder = serializers.PrimaryKeyRelatedField(queryset=Investor.objects.none())
    bank_id = serializers.PrimaryKeyRelatedField(
        source="bank", queryset=BankAccount.objects.none(), required=False, write_only=True
    )
    handle = serializers.CharField(required=False, max_length=120)
    handle_masked = serializers.CharField(read_only=True)

    class Meta:
        model = UPIHandle
        fields = (
            "id",
            "holder",
            "bank_id",
            "handle",
            "handle_masked",
            "active",
            "verified",
            "count_limit_override",
            "amount_limit_override",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "handle_masked", "verified", "created_at", "updated_at")

    def get_fields(self):
        fields = super().get_fields()
        bank = self.context.get("bank")
        if bank is not None:
            fields["holder"].queryset = Investor.objects.filter(workspace=bank.workspace)
            fields["bank_id"].queryset = BankAccount.objects.filter(workspace=bank.workspace)
        return fields

    def validate_handle(self, value):
        normalized = value.strip().lower()
        if not UPI_PATTERN.fullmatch(normalized):
            raise serializers.ValidationError("Enter a valid UPI ID.")
        bank = self.context["bank"]
        existing = UPIHandle.objects.filter(
            handle_lookup_hash=upi_hash_for_workspace(bank.workspace_id, normalized)
        )
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError("This UPI ID is already in this workspace.")
        return normalized

    def validate(self, attrs):
        bank = attrs.get("bank", self.context["bank"])
        if self.instance is None and "handle" not in attrs:
            raise serializers.ValidationError({"handle": "UPI ID is required."})
        if self.instance is None and "bank" in attrs and bank != self.context["bank"]:
            raise serializers.ValidationError({"bank_id": "Choose the bank from the account page."})
        if (
            self.instance is not None
            and bank != self.instance.bank
            and self.instance.applications.exists()
        ):
            raise serializers.ValidationError(
                {"bank_id": "This UPI is used by an application. Add a new UPI for another bank."}
            )
        if self.instance is None and (bank.is_placeholder or not bank.active):
            raise serializers.ValidationError(
                {"bank": "Complete and activate the bank account before adding a UPI ID."}
            )
        effective_active = attrs.get("active", self.instance.active if self.instance else True)
        if effective_active and (bank.is_placeholder or not bank.active):
            raise serializers.ValidationError(
                {"bank_id": "Complete and activate the linked bank account first."}
            )
        holder = attrs.get("holder", getattr(self.instance, "holder", None))
        if effective_active and not holder.active:
            raise serializers.ValidationError({"holder": "Activate the UPI holder first."})
        return attrs

    def create(self, validated_data):
        handle = validated_data.pop("handle")
        validated_data.pop("bank", None)
        upi = UPIHandle(bank=self.context["bank"], **validated_data)
        upi.set_handle(handle)
        upi.save()
        return upi

    def update(self, instance, validated_data):
        handle = validated_data.pop("handle", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if handle is not None:
            instance.set_handle(handle)
        instance.save()
        return instance


class RecurringDebitSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecurringDebit
        fields = (
            "id",
            "name",
            "amount",
            "frequency",
            "start_date",
            "next_due_date",
            "end_date",
            "active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        extra_kwargs = {"next_due_date": {"required": False}}

    def validate(self, attrs):
        start_date = attrs.get("start_date", getattr(self.instance, "start_date", None))
        next_due_date = attrs.get("next_due_date", getattr(self.instance, "next_due_date", None))
        if next_due_date is None and start_date is not None:
            attrs["next_due_date"] = start_date
            next_due_date = start_date
        end_date = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start_date and next_due_date and next_due_date < start_date:
            raise serializers.ValidationError(
                {"next_due_date": "Next date cannot be before the start date."}
            )
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError(
                {"end_date": "End date cannot be before the start date."}
            )
        return attrs

    def create(self, validated_data):
        return RecurringDebit.objects.create(bank=self.context["bank"], **validated_data)


class FundingPreferenceSerializer(serializers.ModelSerializer):
    bank = serializers.PrimaryKeyRelatedField(queryset=BankAccount.objects.none())
    enabled = serializers.BooleanField(default=True)

    class Meta:
        model = FundingPreference
        fields = ("id", "bank", "priority", "enabled", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def get_fields(self):
        fields = super().get_fields()
        beneficiary = self.context.get("beneficiary")
        if beneficiary is not None:
            fields["bank"].queryset = BankAccount.objects.filter(
                workspace=beneficiary.workspace
            ).exclude(owner=beneficiary)
        return fields

    def validate(self, attrs):
        bank = attrs.get("bank", getattr(self.instance, "bank", None))
        beneficiary = self.context["beneficiary"]
        if bank is not None:
            existing = FundingPreference.objects.filter(beneficiary=beneficiary, bank=bank)
            if self.instance is not None:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError(
                    {"bank": "This account is already preferred for this investor."}
                )
        return attrs

    def create(self, validated_data):
        return FundingPreference.objects.create(
            beneficiary=self.context["beneficiary"], **validated_data
        )
