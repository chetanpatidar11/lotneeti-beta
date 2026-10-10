from django.urls import path
from rest_framework.routers import SimpleRouter

from accounts.auth_views import (
    LocalPreviewLoginView,
    LogoutView,
    MeView,
    PasswordLoginView,
    PasswordResetCompleteView,
    PasswordResetStartView,
    RegisterVerifyView,
    RegisterView,
    SessionRefreshView,
)
from accounts.views import WorkspaceViewSet

router = SimpleRouter()
router.register("workspaces", WorkspaceViewSet, basename="workspace")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/register/verify/", RegisterVerifyView.as_view(), name="register-verify"),
    path("auth/password/login/", PasswordLoginView.as_view(), name="password-login"),
    path(
        "auth/password/reset/start/", PasswordResetStartView.as_view(), name="password-reset-start"
    ),
    path(
        "auth/password/reset/complete/",
        PasswordResetCompleteView.as_view(),
        name="password-reset-complete",
    ),
    path("auth/local-preview/", LocalPreviewLoginView.as_view(), name="local-preview-login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/session/refresh/", SessionRefreshView.as_view(), name="session-refresh"),
    path("me/", MeView.as_view(), name="me"),
] + router.urls
