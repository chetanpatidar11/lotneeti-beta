import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient
from test_ipos import issue

from accounts.models import User
from ipos.content import publish_content_revision, queue_content_version
from ipos.models import IPOContentRevision, IPOContentVersion


@pytest.mark.django_db
def test_content_is_queued_once_and_founder_editor_retains_history_and_public_summary():
    founder = User.objects.create_superuser(email="founder@example.invalid", password="test")
    ipo = issue(publication_state="PUBLISHED")
    ipo.save()
    version, created = queue_content_version(
        ipo=ipo,
        content_type="COMPANY",
        source_document_id="synthetic-rhp-v1",
        source_document_url="https://example.invalid/rhp-v1",
        provider_key="manual",
        model_name="local-fixture",
        prompt_version="v1",
        draft_text="Synthetic company builds useful products.",
    )
    duplicate, duplicate_created = queue_content_version(
        ipo=ipo,
        content_type="COMPANY",
        source_document_id="synthetic-rhp-v1",
        provider_key="manual",
        model_name="local-fixture",
        draft_text="This draft must not replace the original.",
    )
    assert created is True
    assert duplicate_created is False
    assert duplicate.pk == version.pk
    assert version.draft_text == "Synthetic company builds useful products."

    staff = Client()
    staff.force_login(founder)
    detail_url = reverse("founder_admin:ai-content-detail", args=[version.pk])
    assert staff.get(detail_url).status_code == 302
    session = staff.session
    session["admin_mfa_verified"] = True
    session.save()
    assert staff.get(reverse("founder_admin:ai-content")).status_code == 200
    assert (
        staff.post(
            detail_url,
            {"action": "publish", "text": "Reviewed company summary.", "reason": "Founder review"},
        ).status_code
        == 302
    )
    assert (
        staff.post(
            detail_url,
            {"action": "publish", "text": "Updated company summary.", "reason": "Correction"},
        ).status_code
        == 302
    )
    version.refresh_from_db()
    assert version.draft_text == "Synthetic company builds useful products."
    assert version.review_state == IPOContentVersion.ReviewState.REVIEWED
    assert IPOContentRevision.objects.filter(content_version=version).count() == 2

    public = APIClient()
    public.force_authenticate(founder)
    response = public.get(reverse("ipo-detail", args=[ipo.pk]))
    assert response.data["company_summary"] == "Updated company summary."
    assert response.data["financial_summary"] is None
    assert response.data["risk_summary"] is None


@pytest.mark.django_db
def test_content_publication_requires_reason_and_nonempty_text():
    founder = User.objects.create_superuser(email="founder@example.invalid", password="test")
    ipo = issue()
    ipo.save()
    version, _ = queue_content_version(
        ipo=ipo,
        content_type="RISK",
        source_document_id="synthetic-rhp-v1",
        draft_text="Risk draft",
    )
    with pytest.raises(ValidationError):
        publish_content_revision(version=version, text="", reason="reason", actor=founder)
    with pytest.raises(ValidationError):
        publish_content_revision(version=version, text="Risk", reason="", actor=founder)
