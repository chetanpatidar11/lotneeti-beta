import json
import logging

import pytest
from django.test import Client
from django.urls import reverse

from core.observability import SafeJSONFormatter, logged_provider_operation
from funding.tasks import run_due_recurring_debits


def test_request_log_is_searchable_without_query_cookie_or_body(caplog):
    client = Client()
    with caplog.at_level(logging.INFO, logger="lotneeti.request"):
        response = client.get(
            f"{reverse('api-v1-health')}?token=SYNTHETIC_PRIVATE_VALUE",
            HTTP_COOKIE="sessionid=SYNTHETIC_PRIVATE_VALUE",
        )
    record = next(item for item in caplog.records if item.name == "lotneeti.request")
    payload = json.loads(SafeJSONFormatter().format(record))
    assert payload["event"] == "request.completed"
    assert payload["status"] == 200
    assert payload["route"] == "api/v1/health/"
    assert payload["request_id"] == response["X-Request-ID"]
    assert "SYNTHETIC_PRIVATE_VALUE" not in json.dumps(payload)


def test_provider_and_job_errors_log_types_without_exception_text(caplog, monkeypatch):
    @logged_provider_operation("synthetic", "refresh")
    def broken_provider():
        raise ValueError("SYNTHETIC_PRIVATE_VALUE")

    def broken_job():
        raise RuntimeError("SYNTHETIC_PRIVATE_VALUE")

    monkeypatch.setattr("funding.tasks.post_due_recurring_debits", broken_job)
    with caplog.at_level(logging.ERROR, logger="lotneeti"):
        with pytest.raises(ValueError):
            broken_provider()
        with pytest.raises(RuntimeError):
            run_due_recurring_debits()
    payloads = [
        json.loads(SafeJSONFormatter().format(item))
        for item in caplog.records
        if item.name.startswith("lotneeti.")
    ]
    assert {item["event"] for item in payloads} == {"provider.failed", "job.failed"}
    assert {item["error_type"] for item in payloads} == {"ValueError", "RuntimeError"}
    assert "SYNTHETIC_PRIVATE_VALUE" not in json.dumps(payloads)
