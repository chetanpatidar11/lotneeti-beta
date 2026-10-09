"""Resolve discovery, exchange detail, and documents before completeness review."""

from datetime import date

from ipos.models import IPOEnrichmentObservation

PLANNING_FIELDS = (
    "lower_price",
    "upper_price",
    "lot_size",
    "open_date",
    "close_date",
    "allotment_date",
)
DOCUMENT_ORDER = {"RHP": 1, "PROSPECTUS": 2, "ADDENDUM": 3, "CORRIGENDUM": 4}


def resolve_enriched_issue(discovered: dict, observations: list[IPOEnrichmentObservation]) -> dict:
    """Do not diagnose missing facts until attempted enrichment is considered."""

    # Keep earlier extractor versions. A newer parser returning no value must
    # never erase a valid fact extracted from the same immutable document.
    attempts = sorted(
        observations,
        key=lambda item: (item.fetched_at, item.normalizer_version, str(item.pk)),
    )
    detail = {}
    detail_facts = {"nse": {}, "bse": {}}
    documents = []
    attempted = []
    errors = []
    for item in attempts:
        key = f"{item.source_key}_{item.stage.lower()}"
        if key not in attempted:
            attempted.append(key)
        if item.outcome == "ERROR":
            errors.append({"source": key, "error": item.safe_error or "unavailable"})
            continue
        if item.stage == "DETAIL":
            detail[item.source_key] = item
            detail_facts.setdefault(item.source_key, {}).update(
                {
                    key: value
                    for key, value in item.normalized_payload.get("facts", {}).items()
                    if value is not None and value != ""
                }
            )
        elif item.stage == "DOCUMENT":
            documents.append(item)
    successful_keys = {f"{key}_detail" for key in detail} | {
        f"{item.source_key}_document" for item in documents
    }
    errors = [item for item in errors if item["source"] not in successful_keys]
    source_market = discovered.get("source_market") or (
        "NSE_EMERGE" if discovered.get("issue_type") == "SME" else "NSE_MAINBOARD"
    )
    own_exchange = "bse" if source_market.startswith("BSE_") else "nse"
    blocking_errors = [
        error for error in errors if error["source"] == f"{own_exchange}_detail" and not detail
    ]

    facts = {
        field: discovered[field] for field in PLANNING_FIELDS if discovered.get(field) is not None
    }
    field_sources = {field: f"{own_exchange.upper()}_LIST" for field in facts}
    nse_facts = detail_facts["nse"]
    bse_facts = detail_facts["bse"]
    listing_identity = {
        field: discovered.get(field) or ""
        for field in ("listing_platform", "listing_exchanges", "designated_exchange")
    }
    documents.sort(
        key=lambda item: (
            item.normalized_payload.get("document_date") or date.min.isoformat(),
            DOCUMENT_ORDER.get(item.normalized_payload.get("document_type"), 0),
            item.source_key,
            item.payload_hash,
            item.normalizer_version,
            item.fetched_at,
        )
    )
    for item in documents:
        for field, value in item.normalized_payload.get("listing_identity", {}).items():
            if field in listing_identity and value:
                listing_identity[field] = value
    if source_market == "NSE_EMERGE":
        listing_identity.update(
            listing_platform="SME", listing_exchanges="NSE", designated_exchange="NSE"
        )
    elif source_market == "BSE_SME":
        listing_identity.update(
            listing_platform="SME", listing_exchanges="BSE", designated_exchange="BSE"
        )
    exchanges = listing_identity["listing_exchanges"]
    conflicts = sorted(
        field
        for field in set(nse_facts) & set(bse_facts)
        if exchanges == "NSE+BSE" and nse_facts[field] != bse_facts[field]
    )
    preferred = (own_exchange, "bse" if own_exchange == "nse" else "nse")
    for source in reversed(preferred):
        for field, value in (bse_facts if source == "bse" else nse_facts).items():
            if value is not None and value != "" and field not in conflicts:
                facts[field] = value
                field_sources[field] = f"{source.upper()}_DETAIL"
    for field in conflicts:
        # Retain the last known valid list value, if any, pending Founder review.
        if field not in discovered:
            facts.pop(field, None)
            field_sources.pop(field, None)

    detail_fields = {field for field, source in field_sources.items() if source.endswith("_DETAIL")}
    for item in documents:
        for field, value in item.normalized_payload.get("facts", {}).items():
            if field not in detail_fields:
                facts[field] = value
                kind = item.normalized_payload.get("document_type", "DOCUMENT")
                field_sources[field] = f"{item.source_key.upper()}_{kind}"

    missing = [field for field in PLANNING_FIELDS if not facts.get(field)]
    review_reasons = []
    if not detail.get(own_exchange):
        review_reasons.append(f"{own_exchange.upper()} issue detail unavailable")
    if not all(listing_identity.values()):
        review_reasons.append("Listing exchange or platform unverified")
    detail_attempted = any(
        item.stage == "DETAIL" and item.source_key == own_exchange for item in attempts
    )
    document_attempted = any(item.stage == "DOCUMENT" for item in attempts)
    if not detail_attempted:
        state = "DISCOVERED"
    elif conflicts or blocking_errors or review_reasons:
        state = "REVIEW_REQUIRED"
    elif missing and not document_attempted and not errors:
        state = "ENRICHING"
    elif missing:
        state = "REVIEW_REQUIRED"
    else:
        state = "READY"
    latest_detail = detail.get(preferred[0]) or detail.get(preferred[1])
    return {
        **discovered,
        **listing_identity,
        "source_market": source_market,
        **facts,
        "missing_planning_fields": missing if state == "REVIEW_REQUIRED" else [],
        "pending_planning_fields": missing if state in {"DISCOVERED", "ENRICHING"} else [],
        "enrichment_state": state,
        "field_sources": field_sources,
        "source_conflict_fields": conflicts,
        "verified_by_multiple_official_sources": (
            exchanges == "NSE+BSE"
            and nse_facts.get("lot_size") is not None
            and nse_facts.get("lot_size") == bse_facts.get("lot_size")
        ),
        "nse_state": (
            "NOT_APPLICABLE" if exchanges == "BSE" else "OK" if detail.get("nse") else "UNAVAILABLE"
        ),
        "bse_state": (
            "NOT_APPLICABLE" if exchanges == "NSE" else "OK" if detail.get("bse") else "UNAVAILABLE"
        ),
        "attempted_sources": attempted,
        "enrichment_errors": errors,
        "blocking_enrichment_errors": blocking_errors,
        "review_reasons": review_reasons,
        "detail_fetched_at": latest_detail.fetched_at.isoformat() if latest_detail else None,
        "detail_source_updated_at": (
            latest_detail.source_updated_at.isoformat()
            if latest_detail and latest_detail.source_updated_at
            else None
        ),
        "rhp_url": next(
            (
                item.normalized_payload.get("links", {}).get("rhp_url")
                for item in detail.values()
                if item.normalized_payload.get("links", {}).get("rhp_url")
            ),
            None,
        ),
    }


def enrich_current_feed_issues(discovered: list[dict]) -> list[dict]:
    symbols = [item["symbol"] for item in discovered]
    grouped: dict[str, list[IPOEnrichmentObservation]] = {symbol: [] for symbol in symbols}
    for item in IPOEnrichmentObservation.objects.filter(symbol__in=symbols):
        grouped[item.symbol].append(item)
    return [resolve_enriched_issue(item, grouped[item["symbol"]]) for item in discovered]
