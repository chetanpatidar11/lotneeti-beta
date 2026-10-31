from django.urls import path

from portfolio.gold_views import GoldListView, GoldPurchaseView, GoldSaleListView, GoldSaleView
from portfolio.views import ProfitReportView, SaleListCreateView

urlpatterns = [
    path("workspaces/<uuid:workspace_id>/gold/", GoldListView.as_view(), name="gold-list"),
    path(
        "workspaces/<uuid:workspace_id>/gold/purchases/<uuid:purchase_id>/",
        GoldPurchaseView.as_view(),
        name="gold-purchase",
    ),
    path(
        "workspaces/<uuid:workspace_id>/gold/sales/",
        GoldSaleListView.as_view(),
        name="gold-sale-list",
    ),
    path(
        "workspaces/<uuid:workspace_id>/gold/sales/<uuid:sale_id>/",
        GoldSaleView.as_view(),
        name="gold-sale",
    ),
    path("workspaces/<uuid:workspace_id>/sales/", SaleListCreateView.as_view(), name="sale-list"),
    path("workspaces/<uuid:workspace_id>/pnl/", ProfitReportView.as_view(), name="profit-report"),
]
