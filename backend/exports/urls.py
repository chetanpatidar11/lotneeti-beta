from django.urls import path

from exports.views import PlanExportCreateView, PlanExportDownloadView

urlpatterns = [
    path(
        "workspaces/<uuid:workspace_id>/planner/runs/<uuid:run_id>/exports/",
        PlanExportCreateView.as_view(),
        name="plan-export-create",
    ),
    path(
        "workspaces/<uuid:workspace_id>/planner/runs/<uuid:run_id>/exports/<uuid:export_id>/download/",
        PlanExportDownloadView.as_view(),
        name="plan-export-download",
    ),
]
