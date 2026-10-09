"""Deterministic extraction of explicitly dated IPO offer timetables."""

import hashlib
import io
import logging
import re
import zipfile
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ipos.models import IPOEnrichmentObservation

MAX_ARCHIVE_BYTES = 80_000_000
MAX_PDF_BYTES = 50_000_000
MAX_PAGES = 1_200
DOCUMENT_EXTRACTOR_VERSION = 5
_DATE = (
    r"(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+)?"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s*\d{1,2},?\s*20\d{2}"
)
_LABELS = {
    "open_date": (
        r"Bid\s*/\s*(?:Offer|Issue)\s+(?:Opening|Opens?)\s+Date|"
        r"Bid\s*/\s*(?:Offer|Issue)\s+Opens?"
    ),
    "close_date": (
        r"Bid\s*/\s*(?:Offer|Issue)\s+(?:Closing|Closes?)\s+Date|"
        r"Bid\s*/\s*(?:Offer|Issue)\s+Closes?"
    ),
    "allotment_date": (
        r"Finali[sz]ation\s+of\s+(?:the\s+)?Basis\s+of\s+Allotment"
        r"(?:\s+with\s+(?:the\s+)?(?:Designated\s+Stock\s+Exchange|NSE\s+EMERGE))?"
    ),
    "refund_or_unblock_date": (
        r"Initiation\s+of\s+(?:Allotment\s*/\s*)?Refunds?"
        r"(?:\s*(?:/|\(|for|from|of|funds|unblocking|Anchor|Investors|ASBA|Account|UPI|ID|linked|bank|if|any|the|\*|\s)){0,90}"
    ),
    "demat_credit_date": (
        r"Credit\s*of\s*Equity\s*Shares\s*to\s*"
        r"(?:Depository|dematerialised|Demat)\s*accounts(?:\s*of\s*Allottees)?"
    ),
    "listing_date": (
        r"Commencement\s+of\s+trading\s+of\s+the\s+Equity\s+Shares\s+on\s+"
        r"(?:the\s+)?Stock\s+Exchange(?:s)?"
    ),
}


def extract_listing_identity(text: str) -> dict[str, str]:
    """Read explicit listing/designated-exchange statements from a prospectus cover."""

    compact = " ".join(text.split())
    listing = re.search(
        r"(?:proposed\s+to\s+be\s+listed|listing\s+of\s+the\s+Equity\s+Shares).{0,350}",
        compact,
        re.I,
    )
    context = listing.group(0) if listing else compact[:2000]
    nse = bool(re.search(r"National\s+Stock\s+Exchange|\bNSE\b", context, re.I))
    bse = bool(re.search(r"BSE\s+Limited|\bBSE\b", context, re.I))
    emerge = bool(re.search(r"NSE\s*EMERGE|EMERGE\s+Platform", compact[:2500], re.I))
    bse_sme = bool(re.search(r"BSE\s+SME|SME\s+Platform\s+of\s+BSE", compact[:2500], re.I))
    designated = None
    for pattern in (
        r"\b(NSE|BSE)\b.{0,35}(?:shall\s+be|is|will\s+be)\s+(?:the\s+)?Designated\s+Stock\s+Exchange",
        r"Designated\s+Stock\s+Exchange\s+(?:shall\s+be|is|will\s+be)\s+(?:the\s+)?\b(NSE|BSE)\b",
        r"Designated\s+Stock\s+Exchange\s+will\s+be\s+(?:the\s+)?(?:National\s+Stock\s+Exchange|BSE\s+Limited)",
    ):
        match = re.search(pattern, context, re.I) or re.search(pattern, compact[:20000], re.I)
        if match:
            designated = (
                match.group(1).upper()
                if match.lastindex
                else ("NSE" if "National" in match.group(0) else "BSE")
            )
            break
    return {
        "listing_platform": "SME" if emerge or bse_sme else "MAINBOARD" if listing else "",
        "listing_exchanges": "NSE+BSE" if nse and bse else "NSE" if nse else "BSE" if bse else "",
        "designated_exchange": designated or "",
        "listing_evidence": context[:500] if listing else "",
    }


def _read_date(text: str) -> str:
    cleaned = re.sub(r"^(?:On or about\s+)", "", text.strip(), flags=re.I)
    cleaned = re.sub(r"^(?:On or before\s+)", "", cleaned, flags=re.I)
    cleaned = re.sub(
        r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"([A-Za-z])(\d)", r"\1 \2", cleaned)
    cleaned = re.sub(r",(\d)", r", \1", cleaned)
    return datetime.strptime(cleaned, "%B %d, %Y").date().isoformat()


def extract_timetable(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Read labelled dates only from an explicitly identified indicative timetable."""

    normalized_text = " ".join(text.split())
    marker = re.search(
        r"indicative (?:timetable|timeline)|events? indicative dates|"
        r"period of subscription list|bid/offerclosingdate|bid/issue closing date",
        normalized_text,
        re.I,
    )
    if not marker:
        return {}, {}
    section = normalized_text[marker.start() : marker.start() + 3_600]
    facts: dict[str, str] = {}
    evidence: dict[str, str] = {}
    for field, label in _LABELS.items():
        label_match = re.search(label, section, re.I)
        if not label_match:
            continue
        tail = section[label_match.end() : label_match.end() + 150]
        match = re.search(rf"On\s+or\s+(?:about|before)\s+({_DATE})", tail, re.I)
        if not match:
            match = re.match(rf"[^A-Za-z]{{0,12}}({_DATE})", tail, re.I)
        if not match:
            continue
        try:
            facts[field] = _read_date(match.group(1))
        except ValueError:
            continue
        evidence[field] = section[label_match.start() : label_match.end() + match.end()][:300]
    return facts, evidence


def _pdf_from_blob(blob: bytes) -> tuple[bytes, str]:
    if len(blob) > MAX_ARCHIVE_BYTES:
        raise ValidationError("Official document exceeds size limit")
    if blob.startswith(b"%PDF-"):
        if len(blob) > MAX_PDF_BYTES:
            raise ValidationError("Official PDF exceeds size limit")
        return blob, "document.pdf"
    if not zipfile.is_zipfile(io.BytesIO(blob)):
        raise ValidationError("Official document is neither PDF nor ZIP")
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        candidates = [
            item
            for item in archive.infolist()
            if item.filename.lower().endswith(".pdf") and not item.is_dir()
        ]
        if not candidates:
            raise ValidationError("Official ZIP contains no PDF")
        choice = max(candidates, key=lambda item: item.file_size)
        if choice.file_size > MAX_PDF_BYTES:
            raise ValidationError("Official PDF exceeds size limit")
        pdf = archive.read(choice)
        if not pdf.startswith(b"%PDF-"):
            raise ValidationError("Official ZIP PDF is invalid")
        return pdf, choice.filename


class NSEOfferDocumentProvider:
    def extract(self, blob: bytes, *, document_type: str, document_date: str | None = None) -> dict:
        pdf, filename = _pdf_from_blob(blob)
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        try:
            reader = PdfReader(io.BytesIO(pdf), strict=False)
            if len(reader.pages) > MAX_PAGES:
                raise ValidationError("Official document has too many pages")
            if document_date is None and reader.pages:
                cover = " ".join((reader.pages[0].extract_text() or "").split())
                dated = re.search(rf"\bDated\s*:?[\s]+({_DATE})", cover, re.I)
                if dated:
                    document_date = _read_date(dated.group(1))
            cover_text = " ".join(
                (reader.pages[index].extract_text() or "")
                for index in range(min(3, len(reader.pages)))
            )
            identity = extract_listing_identity(cover_text)
            facts = {}
            evidence = {}
            page_number = None
            for index, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                page_facts, page_evidence = extract_timetable(text)
                if len(page_facts) > len(facts):
                    facts, evidence = page_facts, page_evidence
                    page_number = index + 1
                if len(facts) == len(_LABELS):
                    break
        except (ValueError, TypeError, OSError, KeyError, PdfReadError) as exc:
            raise ValidationError("Official PDF could not be extracted") from exc
        return {
            "document_type": document_type.upper(),
            "document_date": document_date,
            "document_filename": filename,
            "facts": facts,
            "listing_identity": identity,
            "evidence": evidence,
            "page_number": page_number,
            "review_status": "EXTRACTED" if facts else "REVIEW_REQUIRED",
            "extracted_at": timezone.now().isoformat(),
        }


@transaction.atomic
def record_document_observation(
    *,
    source_key: str,
    symbol: str,
    source_url: str,
    blob: bytes,
    normalized: dict,
    fetched_at=None,
) -> IPOEnrichmentObservation:
    observation, _ = IPOEnrichmentObservation.objects.get_or_create(
        source_key=source_key,
        stage="DOCUMENT",
        symbol=symbol,
        payload_hash=hashlib.sha256(blob).hexdigest(),
        normalizer_version=DOCUMENT_EXTRACTOR_VERSION,
        defaults={
            "source_url": source_url,
            "normalized_payload": normalized,
            "fetched_at": fetched_at or timezone.now(),
        },
    )
    return observation
