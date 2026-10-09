from rest_framework import serializers

from accounts.models import Workspace, WorkspaceMembership
from accounts.services import create_workspace


class WorkspaceSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = (
            "id",
            "name",
            "cross_funding_policy",
            "auto_select_gmp_percent",
            "role",
            "created_at",
        )
        read_only_fields = ("id", "role", "created_at")

    def get_role(self, obj):
        user = self.context["request"].user
        return WorkspaceMembership.objects.get(workspace=obj, user=user).role

    def create(self, validated_data):
        return create_workspace(name=validated_data["name"], owner=self.context["request"].user)
