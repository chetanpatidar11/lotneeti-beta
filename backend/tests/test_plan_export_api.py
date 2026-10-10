from datetime import timedelta
from hashlib import sha256

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from test_planner_persistence import setup_plan

from accounts.models import User, WorkspaceMembership
from core.models import AuditEvent
from exports.models import PlanExport
from exports.storage import DOWNLOAD_TTL_SECONDS, S3ExportStorage
from ipos.models import IPO, IPOUserDecision
from planner.models import PlanRun
from planner.persistence import create_plan_run


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def put(self, key, artifact):
        self.objects[key] = artifact.data

    def signed_url(self, key, *, filename):
        assert key in self.objects
        return f"https://private.example.test/{filename}"


@pytest.mark.django_db
def test_authorized_export_is_private_and_download_rechecks_membership(monkeypatch):
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    storage = FakeStorage()
    monkeypatch.setattr("exports.views.get_export_storage", lambda: storage)
    client = APIClient()
    client.force_authenticate(owner)
    create_url = reverse("plan-export-create", args=[workspace.pk, run.pk])
    created = client.post(create_url, {"format_id": "generic_csv"}, format="json")
    assert created.status_code == 201
    record = PlanExport.objects.get(pk=created.data["id"])
    assert record.object_key.startswith(f"exports/{workspace.pk}/{run.pk}/")
    assert b"TESTX0001A" in storage.objects[record.object_key]
    assert record.plan_output_hash == run.output_hash
    assert record.planner_version == run.planner_version
    assert record.settings_version == run.settings_version
    assert record.input_snapshot_hash == run.input_snapshot_hash
    assert len(record.content_sha256) == 64
    assert record.content_sha256 == sha256(storage.objects[record.object_key]).hexdigest()
    assert (
        AuditEvent.objects.filter(action="planner.export.generated", workspace=workspace).count()
        == 1
    )

    download_url = reverse("plan-export-download", args=[workspace.pk, run.pk, record.pk])
    downloaded = client.get(download_url)
    assert downloaded.status_code == 200
    assert downloaded.data["expires_in_seconds"] == DOWNLOAD_TTL_SECONDS
    assert downloaded.data["download_url"].startswith("https://private.example.test/")
    viewer = User.objects.create_user(email="viewer@example.test")
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    client.force_authenticate(viewer)
    assert client.post(create_url, {}, format="json").status_code == 403
    assert client.get(download_url).status_code == 403
    outsider = User.objects.create_user(email="outsider@example.test")
    client.force_authenticate(outsider)
    assert client.get(download_url).status_code == 404


@pytest.mark.django_db
def test_blocking_plan_cannot_generate_export(monkeypatch):
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    run.status = PlanRun.Status.BLOCKED
    run.save(update_fields=["status"])
    storage = FakeStorage()
    monkeypatch.setattr("exports.views.get_export_storage", lambda: storage)
    client = APIClient()
    client.force_authenticate(owner)
    response = client.post(reverse("plan-export-create", args=[workspace.pk, run.pk]), {})
    assert response.status_code == 409
    assert PlanExport.objects.count() == 0
    assert storage.objects == {}


@override_settings(EXPORT_S3_BUCKET="private-synthetic-exports")
def test_s3_storage_requires_server_side_encryption_and_short_lived_url():
    class FakeS3:
        def put_object(self, **kwargs):
            self.put_args = kwargs

        def generate_presigned_url(self, method, *, Params, ExpiresIn):
            self.url_args = (method, Params, ExpiresIn)
            return "https://private.example.test/signed"

    from exports.adapters import ExportArtifact

    client = FakeS3()
    storage = S3ExportStorage(client=client)
    storage.put("exports/example.csv", ExportArtifact("generic_csv", "v1", "text/csv", "csv", b"x"))
    assert client.put_args["Bucket"] == "private-synthetic-exports"
    assert client.put_args["ServerSideEncryption"] == "AES256"
    assert client.put_args["CacheControl"] == "private, no-store"
    assert storage.signed_url("exports/example.csv", filename="plan.csv").startswith("https://")
    assert client.url_args[2] == 300


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_reviewed_manual_plan_saves_exact_rows_and_blocks_stale_amount_export(monkeypatch):
    owner, workspace, snapshot = setup_plan()
    ipo = IPO.objects.get(pk=snapshot.ipos[0].id)
    today = timezone.localdate()
    ipo.open_date = today - timedelta(days=1)
    ipo.close_date = today + timedelta(days=2)
    ipo.allotment_date = today + timedelta(days=5)
    ipo.save(update_fields=["open_date", "close_date", "allotment_date"])
    IPOUserDecision.objects.create(
        workspace=workspace, ipo_id=snapshot.ipos[0].id, decision="APPLY"
    )
    row = {
        "ipo": snapshot.ipos[0].id,
        "applicant": snapshot.applicants[0].id,
        "category": "RETAIL",
        "lots": 1,
        "amount": "15000.00",
        "demat": snapshot.demats[0].id,
        "bank": snapshot.banks[0].id,
        "upi": snapshot.upis[0].id,
        "locked": True,
    }
    storage = FakeStorage()
    monkeypatch.setattr("exports.views.get_export_storage", lambda: storage)
    client = APIClient()
    client.force_authenticate(owner)
    save_url = reverse("planner-run-create", args=[workspace.pk])
    saved = client.post(save_url, {"rows": [row]}, format="json")
    assert saved.status_code == 201
    assert saved.data["status"] == "READY"
    run = PlanRun.objects.get(pk=saved.data["id"])
    assert run.rows.get().locked is True
    exported = client.post(reverse("plan-export-create", args=[workspace.pk, run.pk]), {})
    assert exported.status_code == 201
    assert len(storage.objects) == 1

    stale = client.post(save_url, {"rows": [row | {"amount": "14900.00"}]}, format="json")
    assert stale.status_code == 201
    assert stale.data["status"] == "BLOCKED"
    assert stale.data["rows"][0]["amount"] == "14900.00"
    stale_run = PlanRun.objects.get(pk=stale.data["id"])
    assert "INVALID_AMOUNT" in stale_run.rows.get().blocking_reasons
    denied = client.post(reverse("plan-export-create", args=[workspace.pk, stale_run.pk]), {})
    assert denied.status_code == 409
    assert len(storage.objects) == 1

    viewer = User.objects.create_user(email="review-viewer@example.test")
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    client.force_authenticate(viewer)
    assert client.post(save_url, {"rows": [row]}, format="json").status_code == 403
