from django.urls import path

from applications.allotment_views import AllotmentChecksView, RecordAllotmentsView
from applications.views import (
    ApplicationActionView,
    ApplicationBulkView,
    ApplicationListView,
    StartTrackingView,
    WorkspaceOperationsView,
)

urlpatterns = [
    path(
        "workspaces/<uuid:workspace_id>/allotment/checks/",
        AllotmentChecksView.as_view(),
        name="allotment-checks",
    ),
    path(
        "workspaces/<uuid:workspace_id>/allotment/checks/<uuid:check_id>/record/",
        RecordAllotmentsView.as_view(),
        name="allotment-record",
    ),
    path(
        "workspaces/<uuid:workspace_id>/operations/",
        WorkspaceOperationsView.as_view(),
        name="workspace-operations",
    ),
    path(
        "workspaces/<uuid:workspace_id>/applications/",
        ApplicationListView.as_view(),
        name="application-list",
    ),
    path(
        "workspaces/<uuid:workspace_id>/applications/bulk/",
        ApplicationBulkView.as_view(),
        name="application-bulk",
    ),
    path(
        "workspaces/<uuid:workspace_id>/planner/runs/<uuid:run_id>/track/",
        StartTrackingView.as_view(),
        name="application-start-tracking",
    ),
    path(
        "workspaces/<uuid:workspace_id>/applications/<uuid:application_id>/<str:action>/",
        ApplicationActionView.as_view(),
        name="application-action",
    ),
]
