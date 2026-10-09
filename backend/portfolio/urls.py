from django.urls import path

from portfolio.views import ProfitReportView, SaleListCreateView

urlpatterns = [
    path("workspaces/<uuid:workspace_id>/sales/", SaleListCreateView.as_view(), name="sale-list"),
    path("workspaces/<uuid:workspace_id>/pnl/", ProfitReportView.as_view(), name="profit-report"),
]
