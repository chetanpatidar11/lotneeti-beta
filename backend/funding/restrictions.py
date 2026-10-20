"""Exact, normalized matches for founder-managed bank-name funding restrictions."""

import re

from funding.models import BankFundingRestriction


def normalize_bank_name(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def restricted_bank_names() -> frozenset[str]:
    names = set()
    for name, aliases in BankFundingRestriction.objects.filter(active=True).values_list(
        "name", "aliases"
    ):
        names.update(
            normalized
            for value in (name, *aliases.splitlines())
            if (normalized := normalize_bank_name(value))
        )
    return frozenset(names)


def bank_name_restricted(bank_name: str, *, names: frozenset[str] | None = None) -> bool:
    return normalize_bank_name(bank_name) in (
        names if names is not None else restricted_bank_names()
    )
