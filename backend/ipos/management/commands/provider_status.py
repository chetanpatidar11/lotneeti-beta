from django.core.management.base import BaseCommand
from django.utils import timezone

from ipos.models import IPO, GMPObservation, IPOProviderSyncState


def _local_time(value):
    return timezone.localtime(value).isoformat() if value else "never"


class Command(BaseCommand):
    help = "Show concise local live-data provider status"

    def handle(self, *args, **options):
        gmp_state = IPOProviderSyncState.objects.filter(source_key="investorgain").first()
        self.stdout.write(
            f"InvestorGain: {GMPObservation.objects.count()} GMP observations; "
            "automatic slots 00:01 and hourly 09:00–19:00 Asia/Kolkata"
        )
        if gmp_state:
            self.stdout.write(
                f"InvestorGain sync: status {gmp_state.last_status or 'never'}; "
                f"last attempt {_local_time(gmp_state.last_attempt_at)}; "
                f"last success {_local_time(gmp_state.last_success_at)}; "
                f"safe error {gmp_state.last_safe_error or 'none'}"
            )
        self.stdout.write(
            f"Published canonical IPOs: {IPO.objects.filter(publication_state='PUBLISHED').count()}"
        )
