"""Explain which official stage supplied each current planning fact."""

from django.core.management.base import BaseCommand

from ipos.bse_feed import current_bse_issues
from ipos.feed_watch import current_feed_issues
from ipos.gmp_effective import resolve_gmp
from ipos.models import IPO
from ipos.overrides import published_ipos


class Command(BaseCommand):
    help = "Show discovery/detail/document provenance and planner readiness"

    def handle(self, *args, **options):
        plannable_ids = set(published_ipos().values_list("id", flat=True))
        nse_issues = current_feed_issues()
        bse_issues = current_bse_issues()
        counts = {
            market: sum(item["source_market"] == market for item in nse_issues + bse_issues)
            for market in ("NSE_MAINBOARD", "NSE_EMERGE", "BSE_MAINBOARD", "BSE_SME")
        }
        self.stdout.write(
            f"Discovery: NSE Mainboard {counts['NSE_MAINBOARD']}, "
            f"NSE EMERGE {counts['NSE_EMERGE']}, "
            f"BSE Mainboard {counts['BSE_MAINBOARD']}, "
            f"BSE SME {counts['BSE_SME']}"
        )
        issues = nse_issues + bse_issues
        if not issues:
            self.stdout.write("No current saved IPO discoveries")
            return
        for issue in issues:
            symbol = issue["symbol"]
            matches = list(IPO.objects.filter(symbol=symbol))
            canonical = (
                "PUBLISHED"
                if any(item.id in plannable_ids for item in matches)
                else "NOT_PUBLISHED"
            )
            self.stdout.write(f"{symbol} — {issue['issuer_name']}")
            self.stdout.write(
                f"  market: {issue['source_market']}; platform: {issue['listing_platform']}; "
                f"listing: {issue['listing_exchanges']}; designated: {issue['designated_exchange']}"
            )
            self.stdout.write(f"  {issue['source_key'].upper()} list: OK")
            for name in (
                "nse_detail",
                "bse_detail",
                "nse_document",
                "bse_document",
                "sebi_document",
            ):
                value = (
                    "NOT_APPLICABLE"
                    if name == "bse_detail" and issue["bse_state"] == "NOT_APPLICABLE"
                    else "NOT_APPLICABLE"
                    if name == "nse_detail" and issue["nse_state"] == "NOT_APPLICABLE"
                    else "OK"
                    if name in issue["attempted_sources"]
                    and not any(error["source"] == name for error in issue["enrichment_errors"])
                    else "UNAVAILABLE"
                    if name in issue["attempted_sources"]
                    else "DISABLED"
                    if name == "bse_detail"
                    else "NOT ATTEMPTED"
                )
                self.stdout.write(f"  {name.replace('_', ' ').upper()}: {value}")
            for field in ("lot_size", "allotment_date", "upper_price"):
                key = "upper_price" if field == "upper_price" else field
                value = issue.get(key, "MISSING")
                source = issue["field_sources"].get(key, "—")
                self.stdout.write(f"  {field}: {value} [{source}]")
            for field in ("open_date", "close_date", "listing_date"):
                self.stdout.write(
                    f"  {field}: {issue.get(field) or 'UNAVAILABLE'} "
                    f"[{issue['field_sources'].get(field, '—')}]"
                )
            self.stdout.write(
                f"  price_band: {issue.get('lower_price') or 'MISSING'}–"
                f"{issue.get('upper_price') or 'MISSING'}"
            )
            self.stdout.write(f"  canonical: {canonical}")
            self.stdout.write(f"  enrichment: {issue['enrichment_state']}")
            self.stdout.write(
                f"  planner: {'READY' if canonical == 'PUBLISHED' else 'NOT AVAILABLE'}"
            )
            published = next((item for item in matches if item.id in plannable_ids), None)
            if published:
                gmp = resolve_gmp(published)
                if gmp.effective:
                    value = gmp.effective.value_per_share
                    pct = value * 100 / published.upper_price
                    self.stdout.write(
                        f"  GMP: ₹{value} ({pct:.2f}%) · {gmp.source_count} fresh source(s)"
                    )
                else:
                    self.stdout.write("  GMP: UNAVAILABLE")
            else:
                self.stdout.write("  GMP: UNAVAILABLE")
            if issue["missing_planning_fields"]:
                self.stdout.write(f"  missing: {', '.join(issue['missing_planning_fields'])}")
            if issue["pending_planning_fields"]:
                self.stdout.write(f"  pending: {', '.join(issue['pending_planning_fields'])}")
            if issue["source_conflict_fields"]:
                self.stdout.write(f"  conflicts: {', '.join(issue['source_conflict_fields'])}")
            for reason in issue["review_reasons"]:
                self.stdout.write(f"  review: {reason}")
            for error in issue["enrichment_errors"]:
                self.stdout.write(f"  {error['source']}: {error['error']}")
