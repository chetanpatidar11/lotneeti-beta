from decimal import Decimal

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Workspace, WorkspaceMembership
from applications.models import Application
from portfolio.models import Sale
from portfolio.pnl import realized_results
from portfolio.reports import profit_report
from portfolio.services import record_sale


class SaleInputSerializer(serializers.Serializer):
    application = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    price_per_share = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )
    sold_on = serializers.DateField()
    charges = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        default=Decimal("0.00"),
    )


def _result(item, pnl):
    return {
        "id": str(item.pk),
        "application": str(item.application_id),
        "ipo_name": item.application.ipo.issuer_name,
        "applicant_name": item.application.applicant.name,
        "quantity": item.quantity,
        "price_per_share": str(item.price_per_share),
        "sold_on": item.sold_on,
        "charges": str(item.charges),
        "recorded_at": item.recorded_at,
        "gross_proceeds": str(pnl.gross_proceeds),
        "ipo_cost": str(pnl.ipo_cost),
        "realized_profit": str(pnl.realized_profit),
        "roi_percent": str(pnl.roi_percent) if pnl.roi_percent is not None else None,
    }


class SaleListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def _workspace(self, request, workspace_id):
        return get_object_or_404(
            Workspace.objects.filter(memberships__user=request.user), pk=workspace_id
        )

    def get(self, request, workspace_id):
        workspace = self._workspace(request, workspace_id)
        sales = Sale.objects.filter(application__workspace=workspace).select_related(
            "application__ipo", "application__applicant"
        )
        sales = list(sales)
        results = realized_results(sales)
        return Response([_result(item, results[item.pk]) for item in sales])

    def post(self, request, workspace_id):
        workspace = self._workspace(request, workspace_id)
        if not WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=request.user,
            role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.OPERATOR),
        ).exists():
            raise PermissionDenied("Only workspace owners and operators can record sales.")
        serializer = SaleInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        application = get_object_or_404(
            Application.objects.filter(workspace=workspace), pk=data["application"]
        )
        try:
            sale = record_sale(
                application=application,
                actor=request.user,
                quantity=data["quantity"],
                price_per_share=data["price_per_share"],
                sold_on=data["sold_on"],
                charges=data["charges"],
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=409)
        application_sales = list(
            Sale.objects.filter(application=application).select_related(
                "application__ipo", "application__applicant"
            )
        )
        results = realized_results(application_sales)
        return Response(_result(sale, results[sale.pk]), status=201)


class ProfitReportQuerySerializer(serializers.Serializer):
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)

    def validate(self, attrs):
        if (
            attrs.get("from_date")
            and attrs.get("to_date")
            and attrs["from_date"] > attrs["to_date"]
        ):
            raise serializers.ValidationError("Start date must be on or before end date")
        return attrs


class ProfitReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = get_object_or_404(
            Workspace.objects.filter(memberships__user=request.user), pk=workspace_id
        )
        query = ProfitReportQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        sales = list(
            Sale.objects.filter(application__workspace=workspace).select_related(
                "application__ipo", "application__applicant"
            )
        )
        return Response(
            profit_report(
                sales,
                from_date=query.validated_data.get("from_date"),
                to_date=query.validated_data.get("to_date"),
            )
        )
