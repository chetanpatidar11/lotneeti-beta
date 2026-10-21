import json

from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Workspace, WorkspaceMembership
from accounts.permissions import WorkspaceDataPermission
from investors.account_imports import (
    AccountImportError,
    confirm_batch,
    create_image_preview,
    create_preview,
    preview_payload,
)
from investors.models import AccountImportBatch


def _can_reveal(workspace, user):
    return WorkspaceMembership.objects.filter(
        workspace=workspace,
        user=user,
        role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.OPERATOR),
    ).exists()


class AccountImportConfirmSerializer(serializers.Serializer):
    row_numbers = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, allow_empty=False
    )
    bank_details = serializers.DictField(
        child=serializers.DictField(
            child=serializers.CharField(allow_blank=True, trim_whitespace=True)
        ),
        required=False,
    )
    shared_upi_owners = serializers.DictField(child=serializers.CharField(), required=False)


class AccountImportListView(APIView):
    permission_classes = [IsAuthenticated, WorkspaceDataPermission]
    parser_classes = [MultiPartParser, FormParser]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def post(self, request, workspace_id):
        workspace = get_object_or_404(
            Workspace.objects.filter(memberships__user=request.user), pk=workspace_id
        )
        uploaded_file = request.FILES.get("file")
        try:
            if uploaded_file is not None:
                batch = create_preview(
                    workspace=workspace, actor=request.user, uploaded_file=uploaded_file
                )
            elif "image_rows" in request.data:
                raw_rows = request.data["image_rows"]
                if not isinstance(raw_rows, str) or len(raw_rows) > 128 * 1024:
                    raise AccountImportError("The extracted image rows are too large.")
                try:
                    extracted_rows = json.loads(raw_rows)
                except (TypeError, ValueError) as exc:
                    raise AccountImportError("The extracted image rows are invalid.") from exc
                batch = create_image_preview(
                    workspace=workspace,
                    actor=request.user,
                    source_filename=request.data.get("source_filename", ""),
                    extracted_rows=extracted_rows,
                )
            else:
                return Response({"file": "Choose an .xlsx workbook or image."}, status=400)
        except AccountImportError as exc:
            payload = {"detail": str(exc)}
            if exc.errors:
                payload["errors"] = exc.errors
            return Response(payload, status=400)
        return Response(
            preview_payload(batch, reveal_details=_can_reveal(workspace, request.user)),
            status=status.HTTP_201_CREATED,
        )


class AccountImportPreviewView(APIView):
    permission_classes = [IsAuthenticated, WorkspaceDataPermission]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def get_batch(self, request, workspace_id, pk):
        return get_object_or_404(
            AccountImportBatch.objects.filter(workspace__memberships__user=request.user),
            workspace_id=workspace_id,
            pk=pk,
        )

    def get(self, request, workspace_id, pk):
        batch = self.get_batch(request, workspace_id, pk)
        return Response(
            preview_payload(batch, reveal_details=_can_reveal(batch.workspace, request.user))
        )

    def post(self, request, workspace_id, pk):
        batch = self.get_batch(request, workspace_id, pk)
        serializer = AccountImportConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = confirm_batch(
                batch=batch,
                actor=request.user,
                row_numbers=serializer.validated_data.get("row_numbers"),
                bank_details=serializer.validated_data.get("bank_details", {}),
                shared_upi_owners=serializer.validated_data.get("shared_upi_owners", {}),
            )
        except AccountImportError as exc:
            payload = {"detail": str(exc)}
            if exc.errors:
                payload["errors"] = exc.errors
            return Response(payload, status=400)
        return Response(result, status=status.HTTP_200_OK)
