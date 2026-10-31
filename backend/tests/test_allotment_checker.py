from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from test_planner_persistence import setup_plan

from accounts.models import User, WorkspaceMembership
from applications.allotment import create_check, match_bids, record_results, records
from applications.models import AllotmentCheck, AllotmentQuery, AllotmentReview, Application
from applications.registrars import Bid, RegistrarError, parse_bids, resolve_issue
from applications.services import mark_blocked, start_tracking_plan
from applications.tasks import check_allotments, expire_allotment_results
from core.crypto import encrypt_value
from funding.models import BalanceChange, BankAccount
from planner.persistence import create_plan_run


@pytest.fixture
def setup(monkeypatch):
    cache.clear()
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    item = start_tracking_plan(plan_run=run, actor=owner)[0]
    item = mark_blocked(application=item, actor=owner, record_only=True)
    monkeypatch.setattr("applications.tasks.catalogue", lambda p: [])
    monkeypatch.setattr("applications.tasks.resolve_issue", lambda ipo, catalogues: ("kfin", "123"))
    monkeypatch.setattr("applications.tasks.time.sleep", lambda s: None)
    monkeypatch.setattr(
        "applications.tasks.lookup", lambda *a: [Bid(150, applied=150, reference="SYN-01")]
    )
    return owner, workspace, item


def run_check(setup):
    owner, workspace, item = setup
    job, _ = create_check(workspace=workspace, actor=owner, ipo_ids=[])
    check_allotments(str(job.pk))
    job.refresh_from_db()
    review = AllotmentReview.objects.get(query__batch=job)
    return job, review


def row(review, quantity=150, cost="15000.00", **kwargs):
    return {
        "id": review.pk,
        "quantity": quantity,
        "actual_cost": Decimal(cost),
        "source_index": 0,
        **kwargs,
    }


@pytest.mark.django_db
def test_check_is_read_only_encrypted_deduplicated_and_record_is_exactly_once(setup):
    owner, workspace, item = setup
    job, created = create_check(workspace=workspace, actor=owner, ipo_ids=[])
    assert created
    duplicate, created = create_check(workspace=workspace, actor=owner, ipo_ids=[])
    assert not created and duplicate.pk == job.pk
    check_allotments(str(job.pk))
    review = AllotmentReview.objects.get()
    query = review.query
    assert query.state == "FOUND" and review.matched_index == 0
    assert records(query)[0]["quantity"] == 150
    assert "SYN-01" not in query.records_ciphertext
    item.refresh_from_db()
    assert item.status == "BLOCKED" and item.result_at is None
    assert BankAccount.objects.get().current_balance == Decimal("50000")
    assert not BalanceChange.objects.exists()
    # Partial allotment and a manually corrected amount both remain supported.
    payload = row(review, 75, "7400.00")
    changed = record_results(check=job, actor=owner, rows=[payload])
    assert changed[0].status == "ALLOTTED"
    assert changed[0].allotted_quantity == 75
    assert BankAccount.objects.get().current_balance == Decimal("42600")
    assert BalanceChange.objects.count() == 1
    record_results(check=job, actor=owner, rows=[payload])
    assert BalanceChange.objects.count() == 1
    with pytest.raises(ValidationError):
        record_results(check=job, actor=owner, rows=[row(review, 76, "7500")])


@pytest.mark.django_db
def test_no_record_is_not_zero_and_manual_zero_requires_verification(setup, monkeypatch):
    owner, workspace, item = setup
    monkeypatch.setattr("applications.tasks.lookup", lambda *a: [])
    job, review = run_check(setup)
    assert review.matched_index is None and review.query.state == "NOT_FOUND"
    payload = row(review, 0, "0", source_index=None)
    with pytest.raises(ValidationError, match="Verify"):
        record_results(check=job, actor=owner, rows=[payload])
    record_results(check=job, actor=owner, rows=[payload | {"manual_verified": True}])
    item.refresh_from_db()
    assert item.status == "NOT_ALLOTTED" and BankAccount.objects.get().current_balance == 50000
    assert not BalanceChange.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["CHALLENGE", "UNAVAILABLE", "PENDING", "RATE_LIMITED", "REVIEW"])
def test_failed_checks_never_record_zero(setup, monkeypatch, state):
    def fail(*args):
        raise RegistrarError(state)

    monkeypatch.setattr("applications.tasks.lookup", fail)
    job, review = run_check(setup)
    assert job.status == "DONE" and review.query.state == state
    assert records(review.query) == [] and review.matched_index is None
    assert BankAccount.objects.get().current_balance == 50000
    assert Application.objects.get().status == "BLOCKED"


@pytest.mark.django_db
def test_stale_edits_and_expired_checks_cannot_debit(setup):
    owner, _, item = setup
    job, review = run_check(setup)
    Application.objects.filter(pk=item.pk).update(edited_at=timezone.now())
    with pytest.raises(ValidationError, match="changed"):
        record_results(check=job, actor=owner, rows=[row(review)])
    assert BankAccount.objects.get().current_balance == 50000
    AllotmentCheck.objects.filter(pk=job.pk).update(created_at=timezone.now() - timedelta(days=8))
    job.refresh_from_db()
    assert expire_allotment_results() == 1
    assert records(AllotmentQuery.objects.get()) == []
    with pytest.raises(ValidationError, match="expired"):
        record_results(check=job, actor=owner, rows=[row(review)])


@pytest.mark.django_db
def test_submitted_can_record_and_planned_are_excluded(setup):
    owner, workspace, item = setup
    Application.objects.filter(pk=item.pk).update(status="PLANNED", blocked_at=None)
    with pytest.raises(ValidationError, match="No submitted"):
        create_check(workspace=workspace, actor=owner, ipo_ids=[])
    Application.objects.filter(pk=item.pk).update(status="SUBMITTED")
    job, review = run_check(setup)
    result = record_results(check=job, actor=owner, rows=[row(review)])[0]
    assert result.status == "ALLOTTED" and BalanceChange.objects.count() == 1


@pytest.mark.django_db
def test_api_permissions_scope_and_no_store(setup):
    owner, workspace, item = setup
    client = APIClient()
    url = reverse("allotment-checks", args=[workspace.pk])
    assert client.get(url).status_code in {401, 403}
    client.force_authenticate(owner)
    response = client.post(url, {}, format="json")
    assert response.status_code == 202 and response.data["status"] == "DONE"
    assert response["Cache-Control"] == "private, no-store"
    review = AllotmentReview.objects.get()
    record_url = reverse("allotment-record", args=[workspace.pk, review.query.batch_id])
    viewer = User.objects.create_user(email="allotment-viewer@example.test")
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    client.force_authenticate(viewer)
    assert client.get(url).status_code == 200
    assert client.post(url, {}, format="json").status_code == 403
    assert client.post(record_url, {}, format="json").status_code == 403
    outsider = User.objects.create_user(email="allotment-outsider@example.test")
    client.force_authenticate(outsider)
    assert client.get(url).status_code == 404
    assert client.post(record_url, {}, format="json").status_code == 404
    client.force_authenticate(owner)
    invalid = {"rows": [{"id": str(review.pk), "quantity": 0, "actual_cost": "-1"}]}
    assert client.post(record_url, invalid, format="json").status_code == 400
    assert client.post(record_url, {"rows": []}, format="json").status_code == 400
    valid = {
        "rows": [{"id": str(review.pk), "quantity": 150, "actual_cost": "15000", "source_index": 0}]
    }
    assert client.post(record_url, valid, format="json").status_code == 200
    assert client.post(record_url, valid, format="json").status_code == 200
    assert BalanceChange.objects.count() == 1


def test_matching_separates_shareholder_ignores_order_and_refuses_ambiguous_lanes():
    demat = SimpleNamespace(
        depository="CDSL",
        dp_id_ciphertext=encrypt_value("", purpose="demat"),
        client_id_ciphertext=encrypt_value("SYN001", purpose="demat"),
    )
    public = SimpleNamespace(
        pk="public", category="RETAIL", lots=1, ipo=SimpleNamespace(lot_size=12), demat=demat
    )
    shareholder = SimpleNamespace(
        pk="share", category="SHARE", lots=13, ipo=public.ipo, demat=demat
    )
    bids = [Bid(60, applied=156), Bid(0, applied=12)]
    assert match_bids([public, shareholder], bids) == {"share": 0, "public": 1}
    assert match_bids([public, shareholder], list(reversed(bids))) == {"public": 0, "share": 1}
    shareholder.lots = 1
    assert match_bids([public, shareholder], [Bid(12, applied=12), Bid(0, applied=12)]) == {}
    assert match_bids([public, shareholder], [Bid(12, applied=12)]) == {}
    assert match_bids([public, shareholder], [Bid(12, category="SHARE")]) == {"share": 0}
    assert match_bids([public], [Bid(12, demat="OTHER")]) == {}
    assert match_bids([public], [Bid(13)]) == {}


def test_provider_parsers_do_not_confuse_empty_missing_challenges_with_zero():
    pan = "TESTX0001A"
    kfin = {"data": [{"Pan_No": pan, "All_Shares": "0", "App_Shares": "12", "Appln_No": "SYN"}]}
    assert parse_bids("kfin", kfin, pan)[0].quantity == 0
    assert parse_bids("kfin", kfin, pan)[0].reference == "SYN"
    masked = {"data": [kfin["data"][0] | {"Pan_No": "XXXXXX001A", "DP_CLID": "SYN-CLIENT"}]}
    assert parse_bids("kfin", masked, pan)[0].demat == "SYN-CLIENT"
    assert parse_bids("kfin", {"data": []}, pan) == []
    for invalid in [
        {"data": [{}]},
        {"data": [{"All_Shares": "pending"}]},
        {"data": [{"All_Shares": "", "Name": "A"}]},
    ]:
        with pytest.raises(RegistrarError):
            parse_bids("kfin", invalid, pan)
    with pytest.raises(RegistrarError):
        parse_bids("kfin", {"data": [kfin["data"][0] | {"Pan_No": "TESTX0002B"}]}, pan)
    with pytest.raises(RegistrarError, match="CHALLENGE"):
        parse_bids("bigshare", {"d": {"Status": "CAPTCHA"}}, pan)
    with pytest.raises(RegistrarError):
        parse_bids("bigshare", {"d": {"ALLOTED": ""}}, pan)
    multi = {
        "d": {
            "Status": "OK",
            "MatchCount": 2,
            "Records": [
                {"ALLOTED": "12", "APPLIED": "12", "APPLICATION_NO": "SYN-P"},
                {"ALLOTED": "24", "APPLIED": "156", "APPLICATION_NO": "SYN-S"},
            ],
        }
    }
    assert [b.quantity for b in parse_bids("bigshare", multi, pan)] == [12, 24]
    assert (
        parse_bids(
            "mufg",
            {"d": "<NewDataSet><Table><ALLOT>0</ALLOT><SHARES>12</SHARES></Table></NewDataSet>"},
            pan,
        )[0].quantity
        == 0
    )
    with pytest.raises(RegistrarError):
        parse_bids("mufg", {"d": "<!DOCTYPE x><x/>"}, pan)


def test_issue_mapping_is_exact_and_refuses_ambiguous_registrars():
    ipo = SimpleNamespace(issuer_name="Synthetic Industries Ltd", close_date=timezone.now().date())
    options = {"kfin": [{"id": "123", "name": "SYNTHETIC INDUSTRIES LIMITED"}]}
    assert resolve_issue(ipo, options) == ("kfin", "123")
    assert resolve_issue(ipo, {"kfin": [{"id": "999", "name": "Synthetic Industry"}]}) is None
    assert resolve_issue(ipo, options | {"mufg": options["kfin"]}) is None


@pytest.mark.django_db
def test_duplicate_review_ids_and_foreign_review_never_debit(setup):
    import uuid

    owner, _, _ = setup
    job, review = run_check(setup)
    with pytest.raises(ValidationError, match="once"):
        record_results(check=job, actor=owner, rows=[row(review), row(review)])
    with pytest.raises(ValidationError, match="belong"):
        record_results(check=job, actor=owner, rows=[row(review) | {"id": uuid.uuid4()}])
    assert not BalanceChange.objects.exists()


@pytest.mark.django_db
def test_batch_is_atomic_and_one_registrar_record_cannot_fund_two_lanes(monkeypatch):
    from django.test import override_settings
    from test_quota_planning import setup_quota

    from planner.models import PlanRun

    cache.clear()
    with override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW"):
        owner, workspace, _, _, _, client = setup_quota(count=1, eligible_count=1)
        payload = client.post(
            reverse("planner-preview", args=[workspace.pk]), {}, format="json"
        ).data
        assert (
            client.post(
                reverse("planner-run-create", args=[workspace.pk]),
                {"rows": payload["rows"]},
                format="json",
            ).status_code
            == 201
        )
        apps = start_tracking_plan(plan_run=PlanRun.objects.get(), actor=owner)
        for item in apps:
            mark_blocked(application=item, actor=owner, record_only=True)
    monkeypatch.setattr("applications.tasks.catalogue", lambda p: [])
    monkeypatch.setattr("applications.tasks.resolve_issue", lambda *a: ("kfin", "123"))
    monkeypatch.setattr("applications.tasks.time.sleep", lambda s: None)
    monkeypatch.setattr("applications.tasks.lookup", lambda *a: [Bid(150), Bid(150)])
    before = list(BankAccount.objects.order_by("pk").values_list("pk", "current_balance"))
    job, _ = create_check(workspace=workspace, actor=owner, ipo_ids=[])
    check_allotments(str(job.pk))
    reviews = list(AllotmentReview.objects.order_by("pk"))
    assert len(reviews) == 2 and all(r.matched_index is None for r in reviews)
    # The first result would debit, but the invalid second row must roll back everything.
    first = row(reviews[0], manual_verified=True)
    second = row(reviews[1], quantity=9999999, manual_verified=True, source_index=1)
    with pytest.raises(ValidationError, match="exceed"):
        record_results(check=job, actor=owner, rows=[first, second])
    assert not BalanceChange.objects.exists()
    assert Application.objects.filter(status="BLOCKED").count() == 2
    with pytest.raises(ValidationError, match="two applications"):
        record_results(check=job, actor=owner, rows=[first, row(reviews[1], manual_verified=True)])
    assert not BalanceChange.objects.exists()
    record_results(
        check=job, actor=owner, rows=[first, row(reviews[1], source_index=1, manual_verified=True)]
    )
    assert BalanceChange.objects.count() == 2
    assert (
        sum(value for _, value in before)
        - sum(BankAccount.objects.values_list("current_balance", flat=True))
        == 30000
    )
    assert AllotmentQuery.objects.get().reviews.count() == 2


@pytest.mark.django_db
def test_duplicate_task_delivery_does_not_requery(setup, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "applications.tasks.lookup", lambda *a: calls.append(a[0]) or [Bid(0, applied=150)]
    )
    job, _ = run_check(setup)
    check_allotments(str(job.pk))
    assert calls == ["kfin"]


def test_http_transport_preserves_header_contract_and_rejects_redirects(monkeypatch):
    from applications import registrars

    calls = []

    class Response:
        status = 200

        def read(self, limit):
            return b'{"data": []}'

    response = Response()

    class Connection:
        def __init__(self, host, **kwargs):
            assert host == "0uz601ms56.execute-api.ap-south-1.amazonaws.com"
            assert kwargs["timeout"] == 6

        def request(self, method, path, **kwargs):
            calls.append((method, path, kwargs))

        def getresponse(self):
            return response

        def close(self):
            pass

    monkeypatch.setattr(registrars.http.client, "HTTPSConnection", Connection)
    assert registrars.lookup("kfin", "123", "TESTX0001A") == []
    headers = calls[0][2]["headers"]
    assert headers["reqparam"] == "TESTX0001A" and headers["client_id"] == "123"
    assert "Reqparam" not in headers and "content-type" not in headers
    assert "TESTX0001A" not in calls[0][1]
    response.status = 302
    with pytest.raises(RegistrarError):
        registrars.lookup("kfin", "123", "TESTX0001A")
    response.status = 429
    with pytest.raises(RegistrarError, match="RATE_LIMITED"):
        registrars.lookup("kfin", "123", "TESTX0001A")


def test_catalogue_loads_current_public_issues_and_negative_caches_outages(monkeypatch):
    from applications import registrars

    cache.clear()
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        if url.endswith(".js"):
            assert kwargs["headers"]["referer"] == registrars.KFIN_SITE
            return (
                'const companies=JSON.parse(\'[{"clientId":"123",'
                '"name":"Synthetic Industries Limited"}]\');'
            )
        return '<script src="./static/js/main.synthetic123.js"></script>'

    monkeypatch.setattr(registrars, "request", get)
    assert registrars.catalogue("kfin") == [{"id": "123", "name": "Synthetic Industries Limited"}]
    assert registrars.catalogue("kfin")[0]["id"] == "123"
    assert len(calls) == 2
    cache.clear()
    monkeypatch.setattr(registrars, "request", lambda *a, **k: "unrecognized HTML")
    assert registrars.catalogue("kfin") == []
    assert cache.get("allotment:catalogue:v1:kfin") == []


@pytest.mark.django_db
def test_queue_staleness_uses_started_time_and_no_job_returns_204(setup):
    from applications.allotment import expire_stale_checks

    owner, workspace, _ = setup
    client = APIClient()
    client.force_authenticate(owner)
    assert client.get(reverse("allotment-checks", args=[workspace.pk])).status_code == 204
    job, _ = create_check(workspace=workspace, actor=owner, ipo_ids=[])
    AllotmentCheck.objects.filter(pk=job.pk).update(
        created_at=timezone.now() - timedelta(hours=1),
        status="RUNNING",
        started_at=timezone.now(),
    )
    expire_stale_checks(workspace)
    job.refresh_from_db()
    assert job.status == "RUNNING"
    AllotmentCheck.objects.filter(pk=job.pk).update(
        started_at=timezone.now() - timedelta(minutes=21)
    )
    expire_stale_checks(workspace)
    job.refresh_from_db()
    assert job.status == "FAILED" and job.queries.get().state == "UNAVAILABLE"


@pytest.mark.parametrize(
    "depository,dp,client,beneficiary",
    [
        ("CDSL", "00000000", "00000001", "0000000000000001"),
        ("NSDL", "IN000000", "00000001", "IN00000000000001"),
    ],
)
def test_matching_uses_complete_depository_identity(depository, dp, client, beneficiary):
    demat = SimpleNamespace(
        depository=depository,
        dp_id_ciphertext=encrypt_value(dp, purpose="demat"),
        client_id_ciphertext=encrypt_value(client, purpose="demat"),
    )
    app = SimpleNamespace(
        pk="synthetic", category="RETAIL", lots=1, ipo=SimpleNamespace(lot_size=12), demat=demat
    )
    assert match_bids([app], [Bid(0, applied=12, demat=beneficiary)]) == {"synthetic": 0}
    assert match_bids([app], [Bid(0, applied=12, demat=client)]) == {}
