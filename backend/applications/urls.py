from django.urls import path

from applications.views import (
    ApplicationActionView,
    ApplicationListView,
    StartTrackingView,
    WorkspaceOperationsView,
)

urlpatterns = [
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
