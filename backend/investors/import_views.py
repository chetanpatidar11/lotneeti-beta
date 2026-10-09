from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Workspace
from accounts.permissions import WorkspaceDataPermission
from investors.account_imports import (
    AccountImportError,
    confirm_batch,
    create_preview,
    preview_payload,
)
from investors.models import AccountImportBatch


class AccountImportConfirmSerializer(serializers.Serializer):
    row_numbers = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, allow_empty=False
    )


class AccountImportListView(APIView):
    permission_classes = [IsAuthenticated, WorkspaceDataPermission]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, workspace_id):
        workspace = get_object_or_404(
            Workspace.objects.filter(memberships__user=request.user), pk=workspace_id
        )
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response({"file": "Upload the approved .xlsx workbook."}, status=400)
        try:
            batch = create_preview(
                workspace=workspace, actor=request.user, uploaded_file=uploaded_file
            )
        except AccountImportError as exc:
            payload = {"detail": str(exc)}
            if exc.errors:
                payload["errors"] = exc.errors
            return Response(payload, status=400)
        return Response(preview_payload(batch), status=status.HTTP_201_CREATED)


class AccountImportPreviewView(APIView):
    permission_classes = [IsAuthenticated, WorkspaceDataPermission]

    def get_batch(self, request, workspace_id, pk):
        return get_object_or_404(
            AccountImportBatch.objects.filter(workspace__memberships__user=request.user),
            workspace_id=workspace_id,
            pk=pk,
        )

    def get(self, request, workspace_id, pk):
        return Response(preview_payload(self.get_batch(request, workspace_id, pk)))

    def post(self, request, workspace_id, pk):
        batch = self.get_batch(request, workspace_id, pk)
        serializer = AccountImportConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = confirm_batch(
                batch=batch,
                actor=request.user,
                row_numbers=serializer.validated_data.get("row_numbers"),
            )
        except AccountImportError as exc:
            payload = {"detail": str(exc)}
            if exc.errors:
                payload["errors"] = exc.errors
            return Response(payload, status=400)
        return Response(result, status=status.HTTP_200_OK)
