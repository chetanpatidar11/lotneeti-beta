import csv
from copy import copy
from dataclasses import replace
from io import StringIO

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from test_export_adapters import sample_row
from test_plan_export_api import FakeStorage
from test_planner_persistence import setup_plan

from exports.demat_csv import DematCSVAdapter
from ipos.models import IPO
from planner.models import PlanRow
from planner.persistence import create_plan_run


def test_demat_csv_has_exact_columns_and_omits_bank_details():
    adapter = DematCSVAdapter()
    cdsl = sample_row(1)
    nsdl = replace(sample_row(2), depository="NSDL", dp_id="DEMO-NSDL-DP")
    output = list(csv.reader(StringIO(adapter.render((cdsl, nsdl)).decode("utf-8"))))
    assert output[0] == [
        "Name",
        "PAN",
        "Type",
        "DPID",
        "CLIENT ID",
        "UPI ID",
        "Account Number",
        "Bank Name",
    ]
    assert output[1] == [
        "Synthetic Investor",
        "TESTX0001A",
        "CDSL",
        "",
        "DEMO-CLIENT-001",
        "demo@upi.test",
        "",
        "",
    ]
    assert output[2][2:4] == ["NSDL", "DEMO-NSDL-DP"]
    assert output[2][-2:] == ["", ""]


@pytest.mark.django_db
def test_ipo_export_is_scoped_and_named_for_one_ipo(monkeypatch):
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    ipo_id = run.rows.first().ipo_ref
    another_ipo = copy(IPO.objects.get(pk=ipo_id))
    another_ipo.pk = None
    another_ipo._state.adding = True
    another_ipo.issuer_name = "Other Synthetic Industries"
    another_ipo.source_record_id = "synthetic-ipo-2"
    another_ipo.save()
    first_row = run.rows.first()
    PlanRow.objects.create(
        plan_run=run,
        position=1,
        ipo_ref=str(another_ipo.pk),
        applicant_ref=first_row.applicant_ref,
        category=first_row.category,
        lots=first_row.lots,
        amount=first_row.amount,
        demat_ref=first_row.demat_ref,
        bank_ref=first_row.bank_ref,
        upi_ref=first_row.upi_ref,
    )
    storage = FakeStorage()
    monkeypatch.setattr("exports.views.get_export_storage", lambda: storage)
    client = APIClient()
    client.force_authenticate(owner)
    create_url = reverse("plan-export-create", args=[workspace.pk, run.pk])
    missing = client.post(create_url, {"format_id": "demat_csv"}, format="json")
    assert missing.status_code == 400
    wrong = client.post(
        create_url, {"format_id": "demat_csv", "ipo_id": "not-in-run"}, format="json"
    )
    assert wrong.status_code == 409
    created = client.post(create_url, {"format_id": "demat_csv", "ipo_id": ipo_id}, format="json")
    assert created.status_code == 201
    assert created.data["row_count"] == 1
    from exports.models import PlanExport

    record = PlanExport.objects.get(pk=created.data["id"])
    assert record.download_filename.startswith("demat-synthetic-industries-")
    assert record.download_filename.endswith(".csv")
    assert b"DEMO-ACCOUNT" not in storage.objects[record.object_key]
    assert len(list(csv.reader(StringIO(storage.objects[record.object_key].decode("utf-8"))))) == 2
    download = client.get(reverse("plan-export-download", args=[workspace.pk, run.pk, record.pk]))
    assert record.download_filename in download.data["download_url"]
