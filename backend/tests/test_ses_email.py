from django.core.mail import EmailMultiAlternatives
from django.test import override_settings

from accounts.ses_email import SESEmailBackend


def test_ses_backend_uses_aws_role_credentials_and_preserves_mime(monkeypatch):
    calls = []

    class SESClient:
        def send_raw_email(self, **kwargs):
            calls.append(kwargs)

    def fake_client(service_name, *, region_name):
        assert service_name == "ses"
        assert region_name == "us-east-1"
        return SESClient()

    monkeypatch.setattr("accounts.ses_email.boto3.client", fake_client)
    message = EmailMultiAlternatives(
        "Sign in to LotNeeti",
        "Open this link to sign in.",
        "founder@example.test",
        ["founder@example.test"],
    )
    message.attach_alternative("<p>Open this link to sign in.</p>", "text/html")

    with override_settings(AWS_SES_REGION="us-east-1"):
        assert SESEmailBackend().send_messages([message]) == 1

    assert len(calls) == 1
    assert calls[0]["Source"] == "founder@example.test"
    assert calls[0]["Destinations"] == ["founder@example.test"]
    assert b"text/html" in calls[0]["RawMessage"]["Data"]


def test_ses_backend_propagates_delivery_errors(monkeypatch):
    class SESClient:
        def send_raw_email(self, **kwargs):
            raise RuntimeError("synthetic delivery failure")

    monkeypatch.setattr("accounts.ses_email.boto3.client", lambda *a, **kw: SESClient())
    message = EmailMultiAlternatives(
        "subject", "body", "founder@example.test", ["founder@example.test"]
    )
    with override_settings(AWS_SES_REGION="us-east-1"):
        try:
            SESEmailBackend().send_messages([message])
        except RuntimeError:
            pass
        else:
            raise AssertionError("SES delivery failure must reach the sign-in request")
