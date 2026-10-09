from django.urls import path

from funding.balance_views import (
    AddMoneyView,
    RecentBalanceChangesView,
    RemoveMoneyView,
    SetBalanceView,
)
from funding.views import (
    BankAccountViewSet,
    FundingPreferenceViewSet,
    RecurringDebitViewSet,
    UPIHandleViewSet,
)

bank_list = BankAccountViewSet.as_view({"get": "list", "post": "create"})
bank_detail = BankAccountViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update", "put": "update"}
)
upi_list = UPIHandleViewSet.as_view({"get": "list", "post": "create"})
upi_detail = UPIHandleViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update", "put": "update"}
)
recurring_list = RecurringDebitViewSet.as_view({"get": "list", "post": "create"})
recurring_detail = RecurringDebitViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update", "put": "update", "delete": "destroy"}
)
preference_list = FundingPreferenceViewSet.as_view({"get": "list", "post": "create"})
preference_detail = FundingPreferenceViewSet.as_view(
    {"patch": "partial_update", "put": "update", "delete": "destroy"}
)

urlpatterns = [
    path(
        "workspaces/<uuid:workspace_id>/investors/<uuid:investor_id>/funding-preferences/",
        preference_list,
        name="funding-preference-list",
    ),
    path(
        "workspaces/<uuid:workspace_id>/investors/<uuid:investor_id>/funding-preferences/<uuid:pk>/",
        preference_detail,
        name="funding-preference-detail",
    ),
    path("workspaces/<uuid:workspace_id>/banks/", bank_list, name="bank-list"),
    path("workspaces/<uuid:workspace_id>/banks/<uuid:pk>/", bank_detail, name="bank-detail"),
    path(
        "workspaces/<uuid:workspace_id>/banks/<uuid:bank_id>/balance-changes/",
        RecentBalanceChangesView.as_view(),
        name="bank-balance-history",
    ),
    path(
        "workspaces/<uuid:workspace_id>/banks/<uuid:bank_id>/balance-changes/add/",
        AddMoneyView.as_view(),
        name="bank-add-money",
    ),
    path(
        "workspaces/<uuid:workspace_id>/banks/<uuid:bank_id>/balance-changes/remove/",
        RemoveMoneyView.as_view(),
        name="bank-remove-money",
    ),
    path(
        "workspaces/<uuid:workspace_id>/banks/<uuid:bank_id>/balance-changes/set/",
        SetBalanceView.as_view(),
        name="bank-set-balance",
    ),
    path("workspaces/<uuid:workspace_id>/banks/<uuid:bank_id>/upis/", upi_list, name="upi-list"),
    path(
        "workspaces/<uuid:workspace_id>/banks/<uuid:bank_id>/upis/<uuid:pk>/",
        upi_detail,
        name="upi-detail",
    ),
    path(
        "workspaces/<uuid:workspace_id>/banks/<uuid:bank_id>/recurring-debits/",
        recurring_list,
        name="recurring-debit-list",
    ),
    path(
        "workspaces/<uuid:workspace_id>/banks/<uuid:bank_id>/recurring-debits/<uuid:pk>/",
        recurring_detail,
        name="recurring-debit-detail",
    ),
]
