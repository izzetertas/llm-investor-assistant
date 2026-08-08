"""FX conversion. All cross-currency arithmetic goes through here.

Rates are 'currency -> USD' as of the report date. To convert between two
non-USD currencies we go via USD, exactly as the dataset guide instructs.
"""

from __future__ import annotations


def to_usd(amount: float, currency: str, fx: dict[str, float]) -> float:
    if currency not in fx:
        raise KeyError(f"No FX rate for currency {currency!r}")
    return amount * fx[currency]


def convert(amount: float, from_ccy: str, to_ccy: str, fx: dict[str, float]) -> float:
    """Convert `amount` from one currency to another, via USD."""
    if from_ccy == to_ccy:
        return amount
    usd = to_usd(amount, from_ccy, fx)
    if to_ccy not in fx:
        raise KeyError(f"No FX rate for currency {to_ccy!r}")
    return usd / fx[to_ccy]
