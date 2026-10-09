from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User, Workspace
from platform_admin.permissions import IsFounderAdmin


class PlatformOverviewView(APIView):
    permission_classes = [IsFounderAdmin]

    def get(self, request):
        return Response(
            {
                "users": User.objects.count(),
                "workspaces": Workspace.objects.count(),
            }
        )
