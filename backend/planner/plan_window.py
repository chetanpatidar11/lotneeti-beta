"""Plan-only closing-day grace metadata shared by preview and export paths."""

import json
from datetime import datetime

from django.core.exceptions import ValidationError

from planner.dto import PlannerSnapshot


def snapshot_is_planning_only(snapshot: PlannerSnapshot) -> bool:
    return any(ipo.cutoff_at <= snapshot.as_of for ipo in snapshot.ipos)


def stored_snapshot_is_planning_only(input_snapshot: str) -> bool:
    try:
        data = json.loads(input_snapshot)
        snapshot = data[0] if isinstance(data, list) else data
        as_of = datetime.fromisoformat(snapshot["as_of"])
        cutoffs = [datetime.fromisoformat(ipo["cutoff_at"]) for ipo in snapshot["ipos"]]
    except (IndexError, KeyError, TypeError, ValueError):
        raise ValidationError("The saved plan snapshot cannot be verified for export") from None
    return any(cutoff <= as_of for cutoff in cutoffs)
