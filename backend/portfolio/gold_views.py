from decimal import Decimal

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Workspace, WorkspaceMembership
from portfolio.gold import create_purchase, gold_report, save_sale, set_removed, update_purchase
from portfolio.models import GoldPurchase, GoldSale


def _workspace(request, workspace_id):
    return get_object_or_404(
        Workspace.objects.filter(memberships__user=request.user), pk=workspace_id
    )


def _writer(workspace, actor):
    if not WorkspaceMembership.objects.filter(
        workspace=workspace, user=actor, role__in=["OWNER", "OPERATOR"]
    ).exists():
        raise PermissionDenied("Only owners and operators can update gold records.")


class PurchaseInput(serializers.Serializer):
    price_mode = serializers.ChoiceField(choices=GoldPurchase.PriceMode.choices, default="LIVE")
    name = serializers.CharField(max_length=120)
    form = serializers.ChoiceField(choices=GoldPurchase.Form.choices)
    owner_name = serializers.CharField(max_length=120, allow_blank=True, default="")
    purity = serializers.CharField(max_length=20)
    purchased_on = serializers.DateField()
    grams = serializers.DecimalField(max_digits=14, decimal_places=6, min_value=Decimal("0.000001"))
    total_cost = serializers.DecimalField(
        max_digits=16, decimal_places=2, min_value=Decimal("0.01")
    )
    current_price_per_gram = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01"), allow_null=True, default=None
    )
    seller = serializers.CharField(max_length=120, allow_blank=True, default="")
    notes = serializers.CharField(max_length=500, allow_blank=True, default="")


class PurchaseCreateInput(PurchaseInput):
    request_id = serializers.UUIDField()


class SaleInput(serializers.Serializer):
    sold_on = serializers.DateField()
    grams = serializers.DecimalField(max_digits=14, decimal_places=6, min_value=Decimal("0.000001"))
    net_proceeds = serializers.DecimalField(
        max_digits=16, decimal_places=2, min_value=Decimal("0.01")
    )
    notes = serializers.CharField(max_length=500, allow_blank=True, default="")


class SaleCreateInput(SaleInput):
    request_id = serializers.UUIDField()
    purchase = serializers.UUIDField()


class GoldView(APIView):
    permission_classes = [IsAuthenticated]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def purchase(self, workspace, pk):
        return get_object_or_404(GoldPurchase, workspace=workspace, pk=pk)

    def sale(self, workspace, pk):
        return get_object_or_404(
            GoldSale.objects.select_related("purchase"), purchase__workspace=workspace, pk=pk
        )

    def change(self, workspace, operation):
        try:
            operation()
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=409)
        return Response(gold_report(workspace))


class GoldListView(GoldView):
    def get(self, request, workspace_id):
        return Response(gold_report(_workspace(request, workspace_id)))

    def post(self, request, workspace_id):
        workspace = _workspace(request, workspace_id)
        _writer(workspace, request.user)
        serializer = PurchaseCreateInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        request_id = data.pop("request_id")
        try:
            _, created = create_purchase(
                workspace=workspace, actor=request.user, request_id=request_id, data=data
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=409)
        return Response(gold_report(workspace), status=201 if created else 200)


class GoldPurchaseView(GoldView):
    def patch(self, request, workspace_id, purchase_id):
        workspace = _workspace(request, workspace_id)
        _writer(workspace, request.user)
        item = self.purchase(workspace, purchase_id)
        serializer = PurchaseInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.change(
            workspace,
            lambda: update_purchase(
                purchase=item, actor=request.user, data=serializer.validated_data
            ),
        )

    def delete(self, request, workspace_id, purchase_id):
        workspace = _workspace(request, workspace_id)
        _writer(workspace, request.user)
        item = self.purchase(workspace, purchase_id)
        return self.change(
            workspace, lambda: set_removed(purchase=item, actor=request.user, removed=True)
        )

    def post(self, request, workspace_id, purchase_id):
        workspace = _workspace(request, workspace_id)
        _writer(workspace, request.user)
        item = self.purchase(workspace, purchase_id)
        return self.change(
            workspace, lambda: set_removed(purchase=item, actor=request.user, removed=False)
        )


class GoldSaleListView(GoldView):
    def post(self, request, workspace_id):
        workspace = _workspace(request, workspace_id)
        _writer(workspace, request.user)
        serializer = SaleCreateInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        purchase = self.purchase(workspace, data.pop("purchase"))
        request_id = data.pop("request_id")
        try:
            _, created = save_sale(
                purchase=purchase, actor=request.user, data=data, request_id=request_id
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=409)
        return Response(gold_report(workspace), status=201 if created else 200)


class GoldSaleView(GoldView):
    def patch(self, request, workspace_id, sale_id):
        workspace = _workspace(request, workspace_id)
        _writer(workspace, request.user)
        item = self.sale(workspace, sale_id)
        serializer = SaleInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.change(
            workspace,
            lambda: save_sale(
                purchase=item.purchase,
                actor=request.user,
                sale=item,
                data=serializer.validated_data,
            ),
        )

    def delete(self, request, workspace_id, sale_id):
        workspace = _workspace(request, workspace_id)
        _writer(workspace, request.user)
        item = self.sale(workspace, sale_id)
        return self.change(
            workspace,
            lambda: set_removed(
                purchase=item.purchase, sale=item, actor=request.user, removed=True
            ),
        )

    def post(self, request, workspace_id, sale_id):
        workspace = _workspace(request, workspace_id)
        _writer(workspace, request.user)
        item = self.sale(workspace, sale_id)
        return self.change(
            workspace,
            lambda: set_removed(
                purchase=item.purchase, sale=item, actor=request.user, removed=False
            ),
        )
