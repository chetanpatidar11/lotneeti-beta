import json
from pathlib import Path

import pytest
from scenario_17_pan import founder_17_snapshot

from planner.engine import generate_proposal

GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures/planner_v2_synthetic_golden.json").read_text()
)


@pytest.mark.parametrize("case", ["retail_17", "scarce_12", "shni_4", "two_ipos_20"])
def test_versioned_synthetic_plan_matches_reviewed_regression_snapshot(case):
    fixtures = {
        "retail_17": founder_17_snapshot(),
        "scarce_12": founder_17_snapshot(balances=("15000.00",) * 12 + ("0.00",) * 5),
        "shni_4": founder_17_snapshot(
            balances=("230000.00",) * 4 + ("15000.00",) * 13,
            mode="SHNI_PREFERRED",
        ),
        "two_ipos_20": founder_17_snapshot(
            balances=("30000.00",) * 3 + ("15000.00",) * 14,
            two_ipos=True,
        ),
    }
    result = generate_proposal(fixtures[case])
    frozen = GOLDEN[case]
    assert result.audit.valid
    assert result.planner_version == frozen["planner_version"]
    assert result.input_snapshot_hash == frozen["input_snapshot_hash"]
    assert result.output_hash == frozen["output_hash"]
    assert [
        {
            "ipo": row.ipo_id,
            "applicant": row.applicant_id,
            "category": row.category,
            "lots": row.lots,
            "amount": str(row.amount),
            "bank": row.bank_id,
            "upi": row.upi_id,
        }
        for row in result.coverage.rows
    ] == frozen["rows"]
    assert [
        {"ipo": item.ipo_id, "applicant": item.applicant_id, "reason": item.reason}
        for item in result.coverage.uncovered
    ] == frozen["uncovered"]
