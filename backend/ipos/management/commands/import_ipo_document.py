"""Review/import a saved official BSE/NSE/SEBI offer document."""

from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from ipos.detail_enrichment import official_document_url
from ipos.document_enrichment import NSEOfferDocumentProvider, record_document_observation


class Command(BaseCommand):
    help = "Extract explicit dates and listing identity from a saved official PDF or ZIP"

    def add_arguments(self, parser):
        parser.add_argument("--symbol", required=True)
        parser.add_argument("--source", required=True, choices=("nse", "bse", "sebi"))
        parser.add_argument("--source-url", required=True)
        parser.add_argument("--file", required=True)
        parser.add_argument(
            "--document-type",
            required=True,
            choices=("RHP", "PROSPECTUS", "CORRIGENDUM", "ADDENDUM"),
        )
        parser.add_argument("--document-date")

    def handle(self, *args, **options):
        path = Path(options["file"]).resolve()
        if path.is_relative_to(Path.cwd()):
            raise CommandError("Saved document must be outside Git")
        if not official_document_url(options["source_url"]):
            raise CommandError("Official HTTPS document URL is required")
        try:
            blob = path.read_bytes()
            normalized = NSEOfferDocumentProvider().extract(
                blob,
                document_type=options["document_type"],
                document_date=options.get("document_date"),
            )
            record_document_observation(
                source_key=options["source"],
                symbol=options["symbol"],
                source_url=options["source_url"],
                blob=blob,
                normalized=normalized,
            )
        except (OSError, ValueError, ValidationError) as exc:
            raise CommandError("Official document could not be imported") from exc
        self.stdout.write(
            f"{options['symbol']}: {normalized['review_status']}, "
            f"{len(normalized['facts'])} explicit timetable facts"
        )
