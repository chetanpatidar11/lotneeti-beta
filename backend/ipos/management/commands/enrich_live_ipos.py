"""Founder-triggered local official-detail enrichment; never called by a customer request."""

import hashlib
import json
import os
import re
import ssl
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

import certifi
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ipos.detail_enrichment import (
    NSEIPOIssueDetailProvider,
    nse_issue_detail_url,
    official_document_url,
    record_detail_observation,
)
from ipos.document_enrichment import (
    DOCUMENT_EXTRACTOR_VERSION,
    NSEOfferDocumentProvider,
    record_document_observation,
)
from ipos.feed_watch import NSE_CURRENT_URL, current_feed_issues, record_nse_current_rows
from ipos.local_publication import publish_local_enriched_issue
from ipos.models import IPOEnrichmentObservation, SEBIFiling
from ipos.sebi_filings import INDEX_URL, document_pdf_url, save_filing_index, search_issuer_filings


def _fetch(url: str, *, max_bytes: int) -> bytes:
    parsed = urlparse(url)
    allowed = {
        "www.nseindia.com",
        "nsearchives.nseindia.com",
        "archives.nseindia.com",
        "www.sebi.gov.in",
    }
    if parsed.scheme != "https" or parsed.hostname not in allowed:
        raise ValueError("Only approved official HTTPS sources are supported")
    context = ssl.create_default_context(cafile=certifi.where())
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; LotNeetiFounderBeta/1.0)",
            "Accept": "application/json, application/pdf, application/zip",
            "Referer": "https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
        },
    )
    with urlopen(request, context=context, timeout=25) as response:
        if urlparse(response.url).hostname not in allowed:
            raise ValueError("Official source redirected to an unsupported host")
        body = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise ValueError("Official response exceeds size limit")
    return body


def _issuer_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower()).removesuffix("limited")


def _record_failure(*, source: str, stage: str, symbol: str, url: str, code: str):
    IPOEnrichmentObservation.objects.get_or_create(
        source_key=source,
        stage=stage,
        symbol=symbol,
        payload_hash=hashlib.sha256(f"{url}:{code}".encode()).hexdigest(),
        defaults={
            "source_url": url,
            "normalized_payload": {"error_code": code},
            "fetched_at": timezone.now(),
            "outcome": "ERROR",
            "safe_error": code,
        },
    )


def _read_or_fetch(path: Path, url: str, *, fetch: bool, max_bytes: int) -> bytes:
    if path.exists():
        body = path.read_bytes()
        if len(body) > max_bytes:
            raise ValueError("Saved official response exceeds size limit")
        return body
    if not fetch:
        raise FileNotFoundError(path.name)
    body = _fetch(url, max_bytes=max_bytes)
    path.write_bytes(body)
    os.chmod(path, 0o600)
    return body


def _document_already_extracted(source: str, symbol: str, blob: bytes) -> bool:
    return IPOEnrichmentObservation.objects.filter(
        source_key=source,
        stage="DOCUMENT",
        symbol=symbol,
        payload_hash=hashlib.sha256(blob).hexdigest(),
        normalizer_version=DOCUMENT_EXTRACTOR_VERSION,
        outcome="OK",
    ).exists()


class Command(BaseCommand):
    help = "Enrich current saved NSE discoveries from official detail and offer documents"

    def add_arguments(self, parser):
        parser.add_argument("--saved-dir", required=True, help="Private directory outside Git")
        parser.add_argument(
            "--fetch", action="store_true", help="Fetch missing official files once"
        )
        parser.add_argument(
            "--refresh-discovery", action="store_true", help="Fetch a new NSE issue list"
        )
        parser.add_argument(
            "--publish-local",
            action="store_true",
            help="Publish complete issues in test SQLite only",
        )
        parser.add_argument("--rights-reference", default="", help="Founder source-use reference")

    def handle(self, *args, **options):
        directory = Path(options["saved_dir"]).resolve()
        if directory.is_relative_to(Path.cwd()):
            raise CommandError("Saved source files must be outside Git")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fetch = options["fetch"]
        if options["refresh_discovery"]:
            if not fetch:
                raise CommandError("--refresh-discovery requires --fetch")
            try:
                raw_list = _fetch(NSE_CURRENT_URL, max_bytes=1_000_000)
                record_nse_current_rows(json.loads(raw_list), observed_at=timezone.now())
                path = directory / "lotneeti-nse-current-latest.json"
                path.write_bytes(raw_list)
                os.chmod(path, 0o600)
            except (ValueError, OSError, ValidationError) as exc:
                raise CommandError("NSE discovery failed; prior saved batch remains") from exc
        issues = [
            issue
            for issue in current_feed_issues()
            if issue.get("status", "").lower() in {"active", "forthcoming"}
        ]
        if not issues:
            self.stdout.write("No active or forthcoming saved NSE discoveries")
            return
        for issue in issues:
            symbol, series = issue["symbol"], "SME" if issue["issue_type"] == "SME" else "EQ"
            detail_url = nse_issue_detail_url(symbol, series)
            detail_path = directory / f"lotneeti-nse-detail-{symbol}.json"
            detail = None
            try:
                blob = _read_or_fetch(detail_path, detail_url, fetch=fetch, max_bytes=2_000_000)
                raw = json.loads(blob)
                detail = NSEIPOIssueDetailProvider().normalize(raw, symbol=symbol, series=series)
                record_detail_observation(
                    source_key="nse",
                    symbol=symbol,
                    source_url=detail_url,
                    raw=raw.get("issueInfo", raw),
                    normalized=detail,
                    fetched_at=datetime.fromtimestamp(detail_path.stat().st_mtime, tz=UTC),
                )
            except (OSError, ValueError, ValidationError, TypeError):
                _record_failure(
                    source="nse",
                    stage="DETAIL",
                    symbol=symbol,
                    url=detail_url,
                    code="DETAIL_UNAVAILABLE",
                )
            if detail:
                rhp_url = official_document_url(detail.get("links", {}).get("rhp_url"))
                if rhp_url:
                    extension = (
                        ".zip" if urlparse(rhp_url).path.lower().endswith(".zip") else ".pdf"
                    )
                    document_path = directory / f"lotneeti-rhp-{symbol.lower()}{extension}"
                    try:
                        blob = _read_or_fetch(
                            document_path, rhp_url, fetch=fetch, max_bytes=80_000_000
                        )
                        if not _document_already_extracted("nse", symbol, blob):
                            normalized = NSEOfferDocumentProvider().extract(
                                blob, document_type="RHP"
                            )
                            record_document_observation(
                                source_key="nse",
                                symbol=symbol,
                                source_url=rhp_url,
                                blob=blob,
                                normalized=normalized,
                                fetched_at=datetime.fromtimestamp(
                                    document_path.stat().st_mtime, tz=UTC
                                ),
                            )
                    except (OSError, ValueError, ValidationError, TypeError):
                        _record_failure(
                            source="nse",
                            stage="DOCUMENT",
                            symbol=symbol,
                            url=rhp_url,
                            code="RHP_UNAVAILABLE",
                        )
            # The regular SEBI index contains only the latest page. Search the
            # official repository by issuer so older RHPs/corrigenda are eligible.
            sebi_search_url = f"{INDEX_URL}&search={quote(issue['issuer_name'])}"
            search_path = directory / f"lotneeti-sebi-search-{symbol.lower()}.html"
            try:
                search_html = _read_or_fetch(
                    search_path, sebi_search_url, fetch=fetch, max_bytes=1_000_000
                ).decode("utf-8", errors="replace")
                matches = search_issuer_filings(issue["issuer_name"], search_html)
                for record in matches:
                    if not SEBIFiling.objects.filter(
                        source_url=record["source_url"], document_url__gt=""
                    ).exists():
                        try:
                            filing_html = _fetch(record["source_url"], max_bytes=1_000_000)
                            pdf_url = document_pdf_url(
                                filing_html.decode("utf-8", errors="replace")
                            )
                            if pdf_url:
                                record["document_url"] = pdf_url
                        except (OSError, ValueError):
                            pass
                if matches:
                    save_filing_index(matches[:100])
            except (OSError, ValueError, ValidationError, UnicodeError):
                _record_failure(
                    source="sebi",
                    stage="INDEX",
                    symbol=symbol,
                    url=sebi_search_url,
                    code="SEBI_SEARCH_UNAVAILABLE",
                )
            filings = [
                filing
                for filing in SEBIFiling.objects.all()
                if _issuer_key(filing.issuer_name) == _issuer_key(issue["issuer_name"])
                and filing.document_type.upper() in {"RHP", "PROSPECTUS", "CORRIGENDUM", "ADDENDUM"}
                and official_document_url(filing.document_url)
            ]
            for filing in sorted(filings, key=lambda item: item.filing_date):
                digest = hashlib.sha256(filing.document_url.encode()).hexdigest()[:12]
                path = directory / f"lotneeti-sebi-{symbol.lower()}-{digest}.pdf"
                try:
                    blob = _read_or_fetch(
                        path, filing.document_url, fetch=fetch, max_bytes=80_000_000
                    )
                    if not _document_already_extracted("sebi", symbol, blob):
                        normalized = NSEOfferDocumentProvider().extract(
                            blob,
                            document_type=filing.document_type,
                            document_date=filing.filing_date.isoformat(),
                        )
                        record_document_observation(
                            source_key="sebi",
                            symbol=symbol,
                            source_url=filing.document_url,
                            blob=blob,
                            normalized=normalized,
                            fetched_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
                        )
                except (OSError, ValueError, ValidationError, TypeError):
                    _record_failure(
                        source="sebi",
                        stage="DOCUMENT",
                        symbol=symbol,
                        url=filing.document_url,
                        code="SEBI_DOCUMENT_UNAVAILABLE",
                    )
            self.stdout.write(
                f"{symbol}: detail {'OK' if detail else 'UNAVAILABLE'}, documents attempted"
            )
        if options["publish_local"]:
            if not options["rights_reference"].strip():
                raise CommandError("--publish-local requires --rights-reference")
            for issue in current_feed_issues():
                if issue["enrichment_state"] != "READY":
                    continue
                try:
                    _, changed = publish_local_enriched_issue(
                        issue, rights_reference=options["rights_reference"]
                    )
                    self.stdout.write(
                        f"{issue['symbol']}: {'published' if changed else 'unchanged'}"
                    )
                except (ValidationError, ValueError):
                    self.stdout.write(f"{issue['symbol']}: publication requires Founder review")
