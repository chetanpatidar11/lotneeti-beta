from datetime import date
from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from ipos.models import IPOProviderSyncState, SEBIFiling
from ipos.sebi_filings import (
    document_pdf_url,
    parse_filing_index,
    save_filing_index,
    search_issuer_filings,
)
from ipos.tasks import sync_sebi_filings

INDEX = """<table><tbody><tr role="row"><td>Sep 24, 2026</td><td><a
href="https://www.sebi.gov.in/filings/public-issues/sep-2026/example-limited-rhp_1.html">
Example Limited - RHP<br>Example Limited - Abridged Prospectus</a></td></tr></tbody></table>"""


def test_index_parser_retains_official_metadata_without_guessing_offer_terms():
    records = parse_filing_index(INDEX)
    assert records == [
        {
            "source_url": "https://www.sebi.gov.in/filings/public-issues/sep-2026/example-limited-rhp_1.html",
            "issuer_name": "Example Limited",
            "document_type": "RHP",
            "filing_date": date(2026, 9, 24),
        }
    ]
    assert "lot_size" not in records[0]
    with pytest.raises(ValidationError, match="no recognized"):
        parse_filing_index("<html>changed schema</html>")


def test_document_parser_accepts_only_official_pdf():
    html = (
        "<iframe src='../../../web/?file=https://www.sebi.gov.in/sebi_data/attachdocs/example.pdf'>"
    )
    assert document_pdf_url(html).endswith("/example.pdf")
    assert document_pdf_url("<iframe src='https://elsewhere.test/example.pdf'>") == ""


def test_official_issuer_search_keeps_exact_issuer_only():
    similar = INDEX.replace("example-limited", "example-limited-industries").replace(
        "Example Limited", "Example Limited Industries"
    )
    assert [
        record["document_type"]
        for record in search_issuer_filings("Example Limited", INDEX + similar)
    ] == ["RHP"]
    assert search_issuer_filings("Other Limited", INDEX) == []


@pytest.mark.django_db
def test_filing_sync_is_idempotent_and_member_watch_is_read_only():
    records = parse_filing_index(INDEX)
    assert save_filing_index(records) == (1, 1)
    filing = SEBIFiling.objects.get()
    filing.document_url = "https://www.sebi.gov.in/sebi_data/attachdocs/example.pdf"
    filing.save(update_fields=["document_url"])
    assert save_filing_index(records) == (0, 1)
    assert SEBIFiling.objects.count() == 1
    assert SEBIFiling.objects.get().review_state == "REVIEW_REQUIRED"
    assert SEBIFiling.objects.get().document_url.endswith("/example.pdf")
    client = APIClient()
    assert client.get(reverse("ipo-filing-watch")).status_code in {401, 403}
    client.force_authenticate(User.objects.create_user(email="reader@example.test"))
    response = client.get(reverse("ipo-filing-watch"))
    assert response.status_code == 200
    assert response.data[0]["issuer_name"] == "Example Limited"


@pytest.mark.django_db
def test_nse_refresh_requires_saved_file_and_never_fetches_website():
    with pytest.raises(CommandError, match="--file, --observed-at"):
        call_command("refresh_nse_ipo_feed", stdout=StringIO())


@pytest.mark.django_db
def test_founder_live_data_page_lists_review_required_filings():
    save_filing_index(parse_filing_index(INDEX))
    founder = User.objects.create_superuser(email="founder@example.test", password="synthetic")
    client = Client()
    client.force_login(founder)
    session = client.session
    session["admin_mfa_verified"] = True
    session.save()
    response = client.get(reverse("founder_admin:live-data"))
    assert response.status_code == 200
    assert b"Example Limited" in response.content
    assert b"REVIEW_REQUIRED" in response.content


@pytest.mark.django_db
def test_sebi_sync_status_is_persistent_and_disabled_source_is_skipped(monkeypatch):
    monkeypatch.setattr("ipos.tasks.sync_sebi_index", lambda: (2, 3))
    assert sync_sebi_filings()["fetched"] == 3
    state = IPOProviderSyncState.objects.get(source_key="sebi")
    assert state.last_attempt_at and state.last_success_at
    assert (state.fetched_count, state.updated_count, state.last_status) == (3, 3, "OK")
    state.enabled = False
    state.save(update_fields=["enabled"])
    assert sync_sebi_filings()["status"] == "DISABLED"


@pytest.mark.django_db
def test_sebi_failure_preserves_last_success_and_records_safe_error(monkeypatch):
    monkeypatch.setattr("ipos.tasks.sync_sebi_index", lambda: (1, 1))
    assert sync_sebi_filings()["status"] == "OK"

    def fail():
        raise OSError("private upstream detail")

    monkeypatch.setattr("ipos.tasks.sync_sebi_index", fail)
    result = sync_sebi_filings()
    assert result == {"status": "ERROR", "provider": "sebi", "error": "OSError"}
    state = IPOProviderSyncState.objects.get(source_key="sebi")
    assert state.last_success_at is not None
    assert state.last_status == "ERROR"
    assert state.last_safe_error == "OSError"
