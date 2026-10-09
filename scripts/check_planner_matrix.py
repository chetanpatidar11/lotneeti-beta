"""Trace every Planner v2 matrix case to an executable pytest function."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs/reference_md/Planner_v2_Test_Matrix.md"
TESTS = ROOT / "backend/tests"

# Cases whose test name does not itself contain the matrix ID. These mappings
# were reviewed against the scenario assertions; the full pytest suite runs them.
ALIASES = {
    "QC-005": (
        "test_planner_upgrades.py::test_qc004_minimum_shni_quote_replaces_retail_without_topping_up",
    ),
    **{
        f"IS-{index:03d}": ("test_ipo_decisions.py::test_matrix_selection_cases",)
        for index in range(1, 7)
    },
    "EL-001": (
        "test_planner_coverage.py::test_inactive_missing_demat_existing_application_and_lock_are_excluded",
    ),
    "EL-002": (
        "test_planner_coverage.py::test_inactive_missing_demat_existing_application_and_lock_are_excluded",
    ),
    "EL-003": (
        "test_planner_coverage.py::test_inactive_missing_demat_existing_application_and_lock_are_excluded",
    ),
    "EL-004": (
        "test_planner_coverage.py::test_cancelled_application_allows_new_row_and_custom_requires_user_choice",
    ),
    "EL-006": (
        "test_planner_wallets.py::test_cf005_cf006_policy_and_el005_to_el007_wallet_eligibility",
    ),
    "AP-001": (
        "test_planner_coverage.py::test_priority_and_ipo_order_with_scarce_capacity",
    ),
    "AP-002": (
        "test_planner_upgrades.py::test_priority_gets_scarce_shni_and_other_retail_row_survives",
    ),
    "AP-003": (
        "test_planner_engine.py::test_ad005_twenty_repeated_runs_have_identical_logical_output_and_hashes",
    ),
    "BA-001": (
        "test_balance_add.py::test_add_money_updates_balance_and_records_immutable_history",
    ),
    "BA-002": (
        "test_balance_remove.py::test_remove_money_decreases_balance_and_records_negative_change",
    ),
    "BA-003": (
        "test_balance_set.py::test_set_balance_replaces_exact_amount_and_records_difference",
    ),
    "BA-004": (
        "test_application_tracking_api.py::test_submitted_then_blocked_updates_capital_without_changing_balance",
    ),
    "BA-005": (
        "test_capital_api.py::test_workspace_capital_uses_latest_saved_plan_and_is_member_scoped",
    ),
    "BA-006": (
        "test_planner_cash.py::test_balance_blocks_planned_and_nonnegative_available",
        "test_planner_locks.py::test_lm002_insufficient_cash_keeps_row_with_blocking_reason",
    ),
    "RD-002": (
        "test_planner_cash.py::test_rd001_to_rd006_scheduled_payments_due_by_cutoff_only",
    ),
    "RD-003": (
        "test_recurring_scheduler.py::test_due_emi_posts_once_and_advances_next_date",
    ),
    "RD-004": (
        "test_planner_cash.py::test_rd001_to_rd006_scheduled_payments_due_by_cutoff_only",
        "test_recurring_scheduler.py::test_paused_emi_does_not_post_and_edited_amount_is_used_when_resumed",
    ),
    "RD-005": (
        "test_planner_cash.py::test_rd001_to_rd006_scheduled_payments_due_by_cutoff_only",
        "test_recurring_scheduler.py::test_paused_emi_does_not_post_and_edited_amount_is_used_when_resumed",
    ),
    "BL-001": (
        "test_application_tracking_api.py::test_not_allotted_releases_full_block_without_a_balance_change",
    ),
    "BL-002": (
        "test_application_tracking_api.py::test_full_allotment_debits_actual_cost_once_and_releases_entire_block",
    ),
    "BL-003": (
        "test_application_tracking_api.py::test_partial_shni_allotment_releases_full_mandate_and_deducts_only_actual_cost",
    ),
    "BL-004": (
        "test_planner_cash.py::test_expected_release_is_next_local_day_and_reuse_is_inclusive",
    ),
    "BL-005": (
        "test_application_snapshot_builder.py::test_live_block_releases_next_day_and_actual_allotment_replaces_expectation",
    ),
    "BL-006": (
        "test_application_snapshot_builder.py::test_live_block_releases_next_day_and_actual_allotment_replaces_expectation",
    ),
    "CF-007": (
        "test_planner_wallets.py::test_cf003_cross_funding_fallback_when_own_cash_is_insufficient",
    ),
    "FP-006": (
        "test_planner_wallets.py::test_cf003_cross_funding_fallback_when_own_cash_is_insufficient",
    ),
    "OP-006": (
        "test_planner_wallets.py::test_owner_guard_prefers_safe_cross_bank_when_another_owner_needs_cash",
    ),
    "SH-004": (
        "test_planner_upgrades.py::test_qc004_minimum_shni_quote_replaces_retail_without_topping_up",
    ),
    "SH-006": (
        "test_planner_17_pan_matrix.py::test_ee003_seventeen_pan_shni_preferred_preserves_baseline_then_four_upgrades",
    ),
    "SH-007": (
        "test_planner_upgrades.py::test_qc007_shni_preferred_maximizes_count_without_consuming_extra_lots",
    ),
    "SH-008": ("test_planner_upgrades.py::test_qc006_retail_only_does_not_upgrade",),
    "MI-002": (
        "test_ipo_decisions.py::test_ipo_manual_apply_skip_persists_and_overrides_workspace_threshold",
        "test_planner_ordering.py::test_is007_higher_gmp_precedes_earlier_cutoff_including_manual_selection",
    ),
    "MI-003": (
        "test_planner_preview_api.py::test_preview_respects_manual_skip_and_rejects_explicit_unselected_ipo",
    ),
}


def main() -> None:
    cases = re.findall(
        r"^\| ([A-Z]{2}-\d{3}) \|.*\| (P[012]) \|$",
        MATRIX.read_text(),
        flags=re.MULTILINE,
    )
    functions = {}
    for path in TESTS.glob("test_*.py"):
        for node in ast.parse(path.read_text()).body:
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and node.name.startswith("test_"):
                functions[f"{path.name}::{node.name}"] = node.name
    missing = []
    for case, priority in cases:
        token = case.lower().replace("-", "")
        references = ALIASES.get(case) or tuple(
            name for name, function in functions.items() if token in function
        )
        if not references or any(
            reference not in functions for reference in references
        ):
            missing.append(f"{case} ({priority})")
    if missing:
        raise SystemExit(f"Unmapped Planner v2 cases: {', '.join(missing)}")
    p0_count = sum(priority == "P0" for _, priority in cases)
    p1_count = sum(priority == "P1" for _, priority in cases)
    print(
        f"Planner v2 matrix: {p0_count}/{p0_count} P0 and {p1_count}/{p1_count} P1 cases mapped to executable tests"
    )


if __name__ == "__main__":
    main()
