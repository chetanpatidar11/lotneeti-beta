from django.urls import path

from ipos.views import ManualGMPViewSet, ManualIPOViewSet
from platform_admin.views import PlatformOverviewView

manual_ipo_list = ManualIPOViewSet.as_view({"get": "list", "post": "create"})
manual_ipo_detail = ManualIPOViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update", "put": "update"}
)
manual_gmp_list = ManualGMPViewSet.as_view({"get": "list", "post": "create"})

urlpatterns = [
    path("overview/", PlatformOverviewView.as_view(), name="platform-overview"),
    path("ipos/", manual_ipo_list, name="platform-ipo-list"),
    path("ipos/<uuid:pk>/", manual_ipo_detail, name="platform-ipo-detail"),
    path("ipos/<uuid:ipo_id>/gmp-observations/", manual_gmp_list, name="platform-gmp-list"),
]
