from django.urls import include, path

from platform_admin.admin_site import founder_admin_site

urlpatterns = [
    path("admin/", founder_admin_site.urls),
    path("api/v1/platform/", include("platform_admin.urls")),
    path("api/v1/", include("accounts.urls")),
    path("api/v1/", include("applications.urls")),
    path("api/v1/", include("investors.urls")),
    path("api/v1/", include("funding.urls")),
    path("api/v1/", include("ipos.urls")),
    path("api/v1/", include("planner.urls")),
    path("api/v1/", include("portfolio.urls")),
    path("api/v1/", include("exports.urls")),
    path("api/v1/", include("core.urls")),
]
