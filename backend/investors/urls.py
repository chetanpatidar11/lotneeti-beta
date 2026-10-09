from django.urls import path

from investors.import_views import AccountImportListView, AccountImportPreviewView
from investors.settings_views import SettingsItemsView
from investors.views import DematAccountViewSet, InvestorViewSet

investor_list = InvestorViewSet.as_view({"get": "list", "post": "create"})
investor_detail = InvestorViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update", "put": "update"}
)
demat_list = DematAccountViewSet.as_view({"get": "list", "post": "create"})
demat_detail = DematAccountViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update", "put": "update"}
)

urlpatterns = [
    path(
        "workspaces/<uuid:workspace_id>/settings/items/",
        SettingsItemsView.as_view(),
        name="settings-items",
    ),
    path(
        "workspaces/<uuid:workspace_id>/account-imports/",
        AccountImportListView.as_view(),
        name="account-import-list",
    ),
    path(
        "workspaces/<uuid:workspace_id>/account-imports/<uuid:pk>/",
        AccountImportPreviewView.as_view(),
        name="account-import-preview",
    ),
    path("workspaces/<uuid:workspace_id>/investors/", investor_list, name="investor-list"),
    path(
        "workspaces/<uuid:workspace_id>/investors/<uuid:pk>/",
        investor_detail,
        name="investor-detail",
    ),
    path(
        "workspaces/<uuid:workspace_id>/investors/<uuid:investor_id>/demats/",
        demat_list,
        name="demat-list",
    ),
    path(
        "workspaces/<uuid:workspace_id>/investors/<uuid:investor_id>/demats/<uuid:pk>/",
        demat_detail,
        name="demat-detail",
    ),
]
