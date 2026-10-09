"""Send Django email through SES using the EC2 instance role."""

import boto3
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class SESEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        client = boto3.client("ses", region_name=settings.AWS_SES_REGION)
        sent = 0
        for message in email_messages:
            try:
                client.send_raw_email(
                    Source=message.from_email,
                    Destinations=message.recipients(),
                    RawMessage={"Data": message.message().as_bytes()},
                )
            except Exception:
                if not self.fail_silently:
                    raise
            else:
                sent += 1
        return sent
