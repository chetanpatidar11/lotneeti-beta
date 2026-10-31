from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from applications.allotment import (
    MESSAGES,
    create_check,
    expire_stale_checks,
    record_results,
    records,
)
from applications.models import AllotmentCheck
from applications.tasks import check_allotments
from applications.views import PrivateApplicationView, _result, _results, _workspace, _writer


class CheckRequest(serializers.Serializer):
    ipos = serializers.ListField(child=serializers.UUIDField(), max_length=100, default=list)


class ReviewedResult(serializers.Serializer):
    id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=0, max_value=999999999)
    actual_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"))
    source_index = serializers.IntegerField(
        min_value=0, max_value=99, allow_null=True, default=None
    )
    manual_verified = serializers.BooleanField(default=False)


class RecordRequest(serializers.Serializer):
    rows = ReviewedResult(many=True, allow_empty=False, max_length=500)


def check_data(job):
    expired = job.created_at < timezone.now() - timedelta(days=7)
    reviews = []
    for query in job.queries.select_related("ipo").order_by("pk"):
        bids = [] if expired else records(query)
        for review in query.reviews.select_related(
            "application__ipo", "application__applicant", "application__bank", "application__upi"
        ).order_by("pk"):
            reviews.append(
                {
                    "id": str(review.pk),
                    "query_id": str(query.pk),
                    "application": _result(review.application),
                    "state": "EXPIRED" if expired else query.state,
                    "message": "Run a fresh check"
                    if expired
                    else MESSAGES.get(query.state, "Needs review"),
                    "provider": query.provider,
                    "checked_at": query.checked_at,
                    "records": bids,
                    "matched_index": review.matched_index,
                    "recorded": review.recorded_at is not None,
                    "recorded_index": review.recorded_index,
                    "recorded_quantity": review.recorded_quantity,
                    "recorded_cost": str(review.recorded_cost)
                    if review.recorded_cost is not None
                    else None,
                }
            )
    return {
        "id": str(job.pk),
        "status": job.status,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "rows": reviews,
    }


class AllotmentChecksView(PrivateApplicationView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = _workspace(request, workspace_id)
        job = AllotmentCheck.objects.filter(workspace=workspace).first()
        if job:
            expire_stale_checks(workspace)
            job.refresh_from_db()
        return Response(check_data(job)) if job else Response(status=204)

    def post(self, request, workspace_id):
        workspace = _workspace(request, workspace_id)
        _writer(workspace, request.user)
        serializer = CheckRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            job, created = create_check(
                workspace=workspace, actor=request.user, ipo_ids=serializer.validated_data["ipos"]
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=409)
        if created:
            try:
                check_allotments.apply_async(args=[str(job.pk)], retry=False)
            except Exception:
                job.status = "FAILED"
                job.completed_at = timezone.now()
                job.save(update_fields=["status", "completed_at"])
                job.queries.update(state="UNAVAILABLE")
        job.refresh_from_db()
        return Response(check_data(job), status=202)


class RecordAllotmentsView(PrivateApplicationView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workspace_id, check_id):
        workspace = _workspace(request, workspace_id)
        _writer(workspace, request.user)
        job = get_object_or_404(AllotmentCheck, pk=check_id, workspace=workspace)
        serializer = RecordRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            changed = record_results(
                check=job, actor=request.user, rows=serializer.validated_data["rows"]
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=409)
        return Response({"applications": _results(changed), "check": check_data(job)})
