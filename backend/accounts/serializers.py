from rest_framework import serializers

from accounts.models import Workspace, WorkspaceMembership
from ipos.models import IPO


class WorkspaceSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = (
            "id",
            "name",
            "cross_funding_policy",
            "auto_select_enabled",
            "auto_select_gmp_percent",
            "auto_select_issue_types",
            "role",
            "created_at",
        )
        read_only_fields = ("id", "name", "role", "created_at")

    def get_role(self, obj):
        user = self.context["request"].user
        return WorkspaceMembership.objects.get(workspace=obj, user=user).role

    def validate_auto_select_issue_types(self, value):
        allowed = {IPO.IssueType.MAINBOARD, IPO.IssueType.SME}
        if (
            not isinstance(value, list)
            or not value
            or len(value) != len(set(map(str, value)))
            or any(item not in allowed for item in value)
        ):
            raise serializers.ValidationError("Choose Mainboard, SME, or both.")
        return value
