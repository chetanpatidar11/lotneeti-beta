from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import mixins, serializers, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Workspace, WorkspaceMembership
from accounts.permissions import WorkspaceDataPermission
from core.audit import record_event
from funding.serializers import BankAccountSerializer, UPIHandleSerializer
from investors.models import DematAccount, Investor
from investors.serializers import DematAccountSerializer, InvestorSerializer


class OptionalDematSerializer(serializers.Serializer):
    depository = serializers.ChoiceField(choices=DematAccount.Depository.choices)
    dp_id = serializers.CharField(required=False, allow_blank=True, max_length=32)
    client_id = serializers.CharField(max_length=32)
    broker = serializers.CharField(required=False, allow_blank=True, max_length=120)


class OptionalBankSerializer(serializers.Serializer):
    bank_name = serializers.CharField(max_length=120)
    account_number = serializers.CharField(max_length=120)
    initial_balance = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    upi_handle = serializers.CharField(required=False, allow_blank=True, max_length=120)


class InvestorSetupSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=180)
    pan = serializers.CharField(max_length=10)
    planning_priority = serializers.IntegerField(min_value=1)
    demat = OptionalDematSerializer(required=False)
    bank = OptionalBankSerializer(required=False)


class InvestorSetupView(APIView):
    """Save an investor and optional linked accounts as one unit."""

    permission_classes = [WorkspaceDataPermission]

    def post(self, request, workspace_id):
        workspace = get_object_or_404(
            Workspace.objects.filter(memberships__user=request.user), pk=workspace_id
        )
        form = InvestorSetupSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data
        with transaction.atomic():
            investor_form = InvestorSerializer(
                data={key: data[key] for key in ("name", "pan", "planning_priority")},
                context={"workspace": workspace},
            )
            investor_form.is_valid(raise_exception=True)
            investor = investor_form.save()
            record_event(
                action="investor.created", target=investor, actor=request.user, workspace=workspace
            )
            result = {
                "investor_id": str(investor.pk),
                "demat_id": None,
                "bank_id": None,
                "upi_id": None,
            }

            if "demat" in data:
                demat_form = DematAccountSerializer(
                    data=data["demat"], context={"investor": investor}
                )
                demat_form.is_valid(raise_exception=True)
                demat = demat_form.save()
                record_event(
                    action="demat.created", target=demat, actor=request.user, workspace=workspace
                )
                result["demat_id"] = str(demat.pk)

            if "bank" in data:
                bank_data = {
                    key: value for key, value in data["bank"].items() if key != "upi_handle"
                }
                bank_form = BankAccountSerializer(
                    data={**bank_data, "owner": str(investor.pk)},
                    context={"workspace": workspace, "request": request},
                )
                bank_form.is_valid(raise_exception=True)
                bank = bank_form.save()
                record_event(
                    action="bank.created", target=bank, actor=request.user, workspace=workspace
                )
                result["bank_id"] = str(bank.pk)
                if data["bank"].get("upi_handle"):
                    upi_form = UPIHandleSerializer(
                        data={"holder": str(investor.pk), "handle": data["bank"]["upi_handle"]},
                        context={"bank": bank},
                    )
                    upi_form.is_valid(raise_exception=True)
                    upi = upi_form.save()
                    record_event(
                        action="upi.created", target=upi, actor=request.user, workspace=workspace
                    )
                    result["upi_id"] = str(upi.pk)
        response = Response(result, status=201)
        response["Cache-Control"] = "private, no-store"
        return response


class SensitiveNoStoreMixin:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class InvestorViewSet(
    SensitiveNoStoreMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = InvestorSerializer
    permission_classes = [WorkspaceDataPermission]

    def get_workspace(self):
        return get_object_or_404(
            Workspace.objects.filter(memberships__user=self.request.user),
            pk=self.kwargs["workspace_id"],
        )

    def get_queryset(self):
        return Investor.objects.filter(workspace=self.get_workspace(), is_deleted=False).order_by(
            "planning_priority", "id"
        )

    def get_serializer_context(self):
        workspace = self.get_workspace()
        can_reveal = WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=self.request.user,
            role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.OPERATOR),
        ).exists()
        return {
            **super().get_serializer_context(),
            "workspace": workspace,
            "reveal_details": can_reveal,
        }

    def perform_create(self, serializer):
        with transaction.atomic():
            investor = serializer.save()
            record_event(
                action="investor.created",
                target=investor,
                actor=self.request.user,
                workspace=investor.workspace,
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            investor = serializer.save()
            record_event(
                action="investor.updated",
                target=investor,
                actor=self.request.user,
                workspace=investor.workspace,
            )


class DematAccountViewSet(
    SensitiveNoStoreMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = DematAccountSerializer
    permission_classes = [WorkspaceDataPermission]

    def get_investor(self):
        return get_object_or_404(
            Investor.objects.filter(
                workspace__memberships__user=self.request.user, is_deleted=False
            ),
            pk=self.kwargs["investor_id"],
            workspace_id=self.kwargs["workspace_id"],
        )

    def get_queryset(self):
        return DematAccount.objects.filter(investor=self.get_investor()).order_by("id")

    def get_serializer_context(self):
        investor = self.get_investor()
        can_edit = WorkspaceMembership.objects.filter(
            workspace=investor.workspace,
            user=self.request.user,
            role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.OPERATOR),
        ).exists()
        return {
            **super().get_serializer_context(),
            "investor": investor,
            "reveal_details": self.action == "retrieve" and can_edit,
            "display_details": can_edit,
        }

    def perform_create(self, serializer):
        with transaction.atomic():
            demat = serializer.save()
            record_event(
                action="demat.created",
                target=demat,
                actor=self.request.user,
                workspace=demat.investor.workspace,
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            demat = serializer.save()
            record_event(
                action="demat.updated",
                target=demat,
                actor=self.request.user,
                workspace=demat.investor.workspace,
            )
