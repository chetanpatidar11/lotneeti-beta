from django.core.management.base import BaseCommand

from ipos.models import IPO
from ipos.overrides import effective_ipo_resolution


class Command(BaseCommand):
    help = "List canonical IPO fields needing Founder review"

    def handle(self, *args, **options):
        count = 0
        for ipo in IPO.objects.order_by("issuer_name"):
            result = effective_ipo_resolution(ipo)
            fields = (*result.exchange_conflict_fields, *result.document_disagreement_fields)
            if fields or result.validation_blocked:
                self.stdout.write(
                    f"{ipo.issuer_name}: {', '.join(sorted(set(fields))) or 'validation blocked'}"
                )
                count += 1
        if not count:
            self.stdout.write("No canonical IPO conflicts")
