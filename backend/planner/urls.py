from django.urls import path

from planner.views import (
    PlannerLatestRunView,
    PlannerPreviewView,
    PlannerRunClearView,
    PlannerRunCreateView,
    PlannerValidateView,
    WorkspaceCapitalView,
)

urlpatterns = [
    path(
        "workspaces/<uuid:workspace_id>/planner/runs/latest/",
        PlannerLatestRunView.as_view(),
        name="planner-latest-run",
    ),
    path(
        "workspaces/<uuid:workspace_id>/planner/runs/<uuid:run_id>/clear/",
        PlannerRunClearView.as_view(),
        name="planner-run-clear",
    ),
    path(
        "workspaces/<uuid:workspace_id>/capital/",
        WorkspaceCapitalView.as_view(),
        name="workspace-capital",
    ),
    path(
        "workspaces/<uuid:workspace_id>/planner/preview/",
        PlannerPreviewView.as_view(),
        name="planner-preview",
    ),
    path(
        "workspaces/<uuid:workspace_id>/planner/validate/",
        PlannerValidateView.as_view(),
        name="planner-validate",
    ),
    path(
        "workspaces/<uuid:workspace_id>/planner/runs/",
        PlannerRunCreateView.as_view(),
        name="planner-run-create",
    ),
]
