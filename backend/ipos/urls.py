from django.urls import path

from ipos.decision_views import WorkspaceIPODecisionView, WorkspaceIPOListView
from ipos.public_views import (
    GMPHistoryView,
    IPOFeedWatchView,
    PublicIPOViewSet,
    SEBIFilingWatchView,
)

ipo_list = PublicIPOViewSet.as_view({"get": "list"})
ipo_detail = PublicIPOViewSet.as_view({"get": "retrieve"})

urlpatterns = [
    path(
        "workspaces/<uuid:workspace_id>/ipo-decisions/",
        WorkspaceIPOListView.as_view(),
        name="workspace-ipo-decision-list",
    ),
    path(
        "workspaces/<uuid:workspace_id>/ipo-decisions/<uuid:ipo_id>/",
        WorkspaceIPODecisionView.as_view(),
        name="workspace-ipo-decision-detail",
    ),
    path("ipos/", ipo_list, name="ipo-list"),
    path("ipos/feed-watch/", IPOFeedWatchView.as_view(), name="ipo-feed-watch"),
    path("ipos/filing-watch/", SEBIFilingWatchView.as_view(), name="ipo-filing-watch"),
    path("ipos/<uuid:pk>/", ipo_detail, name="ipo-detail"),
    path("ipos/<uuid:ipo_id>/gmp-history/", GMPHistoryView.as_view(), name="ipo-gmp-history"),
]
