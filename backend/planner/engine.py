"""Deterministic Planner v2 proposal from one immutable input snapshot."""

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256

from planner.audit import AuditResult, audit_plan
from planner.coverage import CoverageResult, baseline_retail_coverage
from planner.dto import PlannerSnapshot, canonical_json
from planner.explanations import explain_rows
from planner.locks import locked_coverage
from planner.repair import owner_affinity_cleanup, repair_shni_upgrades
from planner.upgrades import upgrade_retail_to_shni
from planner.wallets import choose_retail_wallet

PLANNER_VERSION = "planner-v2.0"


@dataclass(frozen=True, slots=True)
class PlannerProposal:
    planner_version: str
    settings_version: str
    input_snapshot_hash: str
    output_hash: str
    coverage: CoverageResult
    audit: AuditResult


def _hash(value: object) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def generate_proposal(snapshot: PlannerSnapshot) -> PlannerProposal:
    if snapshot.config.version != PLANNER_VERSION:
        raise ValueError("Planner input version does not match the running algorithm")
    locked = locked_coverage(snapshot)
    baseline = baseline_retail_coverage(snapshot, choose_retail_wallet, locked.rows)
    upgraded = upgrade_retail_to_shni(snapshot, baseline)
    repaired = repair_shni_upgrades(snapshot, upgraded)
    cleaned = owner_affinity_cleanup(snapshot, repaired)
    explained = explain_rows(snapshot, cleaned)
    total = sum((row.amount for row in explained.rows), Decimal("0.00"))
    audit = audit_plan(snapshot, explained.rows, reported_planned_total=total)
    return PlannerProposal(
        planner_version=PLANNER_VERSION,
        settings_version=f"sha256:{_hash(snapshot.config)}",
        input_snapshot_hash=_hash(snapshot),
        output_hash=_hash((PLANNER_VERSION, explained, audit)),
        coverage=explained,
        audit=audit,
    )
