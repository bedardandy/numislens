"""Pure serializers for API responses."""

from __future__ import annotations


def dollars(cents: int | None) -> str | None:
    if cents is None:
        return None
    return f"${cents / 100:,.2f}"


def serialize_coin(coin: dict | None) -> dict | None:
    if coin is None:
        return None
    out = dict(coin)
    out["value_est_display"] = dollars(coin.get("value_est_cents"))
    out["cost_basis_display"] = dollars(coin.get("cost_basis_cents"))
    return out
