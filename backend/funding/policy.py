"""Resolve cross-funding settings before passing wallets to the planner.

The caller supplies the effective-dated platform value. No global default is
assumed here because the approved specifications leave that value configurable.
"""

from dataclasses import dataclass

POLICIES = {"ALLOW", "WARN", "DISALLOW"}
OVERRIDES = POLICIES | {"DEFAULT"}


@dataclass(frozen=True)
class CrossFundingDecision:
    policy: str
    source: str
    allowed_for_automation: bool
    warnings: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    keep_locked_row: bool


def resolve_cross_funding_policy(
    *,
    platform_default: str,
    bank_policy: str = "DEFAULT",
    workspace_policy: str = "DEFAULT",
    plan_override: str = "DEFAULT",
    locked_row: bool = False,
    same_owner: bool = False,
) -> CrossFundingDecision:
    """Apply explicit overrides; a bank-level prohibition remains a hard guard.

    A locked manual row is preserved for display and validation even when its
    policy is blocking; it never becomes an automatic candidate in that case.
    """
    if platform_default not in POLICIES:
        raise ValueError("A concrete platform cross-funding policy is required")
    for value in (bank_policy, workspace_policy, plan_override):
        if value not in OVERRIDES:
            raise ValueError(f"Unknown cross-funding policy: {value}")

    if same_owner:
        return CrossFundingDecision("ALLOW", "own_account", True, (), (), locked_row)

    policy = platform_default
    source = "platform"
    for name, value in (
        ("bank", bank_policy),
        ("workspace", workspace_policy),
        ("plan", plan_override),
    ):
        if value != "DEFAULT":
            policy, source = value, name

    # CF-006: a bank marked DISALLOW cannot become a cross-funding candidate
    # merely because the wider workspace or plan allows cross-funding.
    if bank_policy == "DISALLOW":
        policy, source = "DISALLOW", "bank"

    allowed = policy != "DISALLOW"
    warnings = ("CROSS_FUNDING",)
    if policy == "WARN":
        warnings += ("CROSS_FUNDING_POLICY_WARNING",)
    return CrossFundingDecision(
        policy=policy,
        source=source,
        allowed_for_automation=allowed,
        warnings=warnings,
        blocking_reasons=() if allowed else ("CROSS_FUNDING_DISALLOWED",),
        keep_locked_row=locked_row,
    )
