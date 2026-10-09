"""Deterministic priority order for final selected IPOs."""

from planner.dto import IPOInput


def selected_ipo_order(ipos: tuple[IPOInput, ...]) -> tuple[IPOInput, ...]:
    return tuple(
        sorted(
            (ipo for ipo in ipos if ipo.selected),
            key=lambda ipo: (
                ipo.gmp_percent is None,
                -ipo.gmp_percent if ipo.gmp_percent is not None else 0,
                ipo.cutoff_at,
                ipo.id,
            ),
        )
    )
