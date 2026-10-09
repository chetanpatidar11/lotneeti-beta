from django.urls import path
from rest_framework.routers import SimpleRouter

from accounts.auth_views import (
    EmailLoginStartView,
    EmailLoginVerifyView,
    LocalPreviewLoginView,
    LogoutView,
    MeView,
)
from accounts.views import WorkspaceViewSet

router = SimpleRouter()
router.register("workspaces", WorkspaceViewSet, basename="workspace")

urlpatterns = [
    path("auth/email/start/", EmailLoginStartView.as_view(), name="email-login-start"),
    path("auth/email/verify/", EmailLoginVerifyView.as_view(), name="email-login-verify"),
    path("auth/local-preview/", LocalPreviewLoginView.as_view(), name="local-preview-login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
] + router.urls
