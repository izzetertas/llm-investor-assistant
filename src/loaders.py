"""CSV loaders. Reads the Meridian mock dataset into typed, indexed in-memory tables.

Pure data access only — no business logic lives here. Every downstream metric
reads from these indexes so the source rows (and their IDs) stay traceable for
citations.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# The dataset's report date. Treated as "today" for anything upcoming/current.
REPORT_DATE = date(2026, 6, 25)


def _read(name: str) -> list[dict[str, str]]:
    path = DATA_DIR / name
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _num(value: str) -> float | None:
    """Parse a CSV cell to float, returning None for blanks."""
    if value is None or value.strip() == "":
        return None
    return float(value)


def _parse_date(value: str) -> date | None:
    if value is None or value.strip() == "":
        return None
    return date.fromisoformat(value.strip())


@dataclass(frozen=True)
class Dataset:
    """All tables, indexed for the access patterns the metrics need."""

    investors: dict[str, dict]
    companies: dict[str, dict]
    deals: dict[str, dict]
    fx: dict[str, float]  # currency -> to_usd

    allocations: list[dict]
    valuations: list[dict]
    capital_calls: list[dict]
    fees: list[dict]
    distributions: list[dict]
    statement_lines: list[dict]

    # Secondary indexes (built in __post_init__-style factory below)
    allocs_by_investor: dict[str, list[dict]] = field(default_factory=dict)
    valuations_by_deal: dict[str, list[dict]] = field(default_factory=dict)
    calls_by_alloc: dict[str, list[dict]] = field(default_factory=dict)
    fees_by_alloc: dict[str, list[dict]] = field(default_factory=dict)
    dists_by_alloc: dict[str, list[dict]] = field(default_factory=dict)
    statement_by_investor: dict[str, list[dict]] = field(default_factory=dict)

    def company_for_deal(self, deal_id: str) -> dict:
        return self.companies[self.deals[deal_id]["company_id"]]


@lru_cache(maxsize=1)
def load_dataset() -> Dataset:
    """Load and index the dataset once. Cached for the process lifetime."""

    investors_raw = _read("investors.csv")
    companies_raw = _read("portfolio_companies.csv")
    deals_raw = _read("deals.csv")
    fx_raw = _read("fx_rates.csv")

    investors = {r["investor_id"]: _coerce_investor(r) for r in investors_raw}
    companies = {r["company_id"]: r for r in companies_raw}
    deals = {r["deal_id"]: _coerce_deal(r) for r in deals_raw}
    fx = {r["currency"]: float(r["to_usd"]) for r in fx_raw}

    allocations = [_coerce_alloc(r) for r in _read("allocations.csv")]
    valuations = [_coerce_valuation(r) for r in _read("valuations.csv")]
    capital_calls = [_coerce_call(r) for r in _read("capital_calls.csv")]
    fees = [_coerce_fee(r) for r in _read("fees.csv")]
    distributions = [_coerce_dist(r) for r in _read("distributions.csv")]
    statement_lines = [_coerce_line(r) for r in _read("statement_lines.csv")]

    allocs_by_investor: dict[str, list[dict]] = defaultdict(list)
    for a in allocations:
        allocs_by_investor[a["investor_id"]].append(a)

    valuations_by_deal: dict[str, list[dict]] = defaultdict(list)
    for v in valuations:
        valuations_by_deal[v["deal_id"]].append(v)
    for rows in valuations_by_deal.values():
        rows.sort(key=lambda r: r["valuation_date"])

    calls_by_alloc: dict[str, list[dict]] = defaultdict(list)
    for c in capital_calls:
        calls_by_alloc[c["allocation_id"]].append(c)

    fees_by_alloc: dict[str, list[dict]] = defaultdict(list)
    for f in fees:
        fees_by_alloc[f["allocation_id"]].append(f)

    dists_by_alloc: dict[str, list[dict]] = defaultdict(list)
    for d in distributions:
        dists_by_alloc[d["allocation_id"]].append(d)

    statement_by_investor: dict[str, list[dict]] = defaultdict(list)
    for ln in statement_lines:
        statement_by_investor[ln["investor_id"]].append(ln)
    for rows in statement_by_investor.values():
        rows.sort(key=lambda r: r["date"])

    return Dataset(
        investors=investors,
        companies=companies,
        deals=deals,
        fx=fx,
        allocations=allocations,
        valuations=valuations,
        capital_calls=capital_calls,
        fees=fees,
        distributions=distributions,
        statement_lines=statement_lines,
        allocs_by_investor=dict(allocs_by_investor),
        valuations_by_deal=dict(valuations_by_deal),
        calls_by_alloc=dict(calls_by_alloc),
        fees_by_alloc=dict(fees_by_alloc),
        dists_by_alloc=dict(dists_by_alloc),
        statement_by_investor=dict(statement_by_investor),
    )


# --- row coercion (str -> typed) -------------------------------------------


def _coerce_investor(r: dict) -> dict:
    return {**r, "age": _num(r["age"]), "onboarded_date": _parse_date(r["onboarded_date"])}


def _coerce_deal(r: dict) -> dict:
    return {
        **r,
        "deal_date": _parse_date(r["deal_date"]),
        "pre_money_valuation_m": _num(r["pre_money_valuation_m"]),
        "post_money_valuation_m": _num(r["post_money_valuation_m"]),
        "round_size_m": _num(r["round_size_m"]),
        "sponsor_allocation_m": _num(r["sponsor_allocation_m"]),
        "entry_share_price": _num(r["entry_share_price"]),
        "contributed_pct": _num(r["contributed_pct"]),
        "std_mgmt_fee_pct": _num(r["std_mgmt_fee_pct"]),
        "std_performance_fee_pct": _num(r["std_performance_fee_pct"]),
        "std_structuring_fee_pct": _num(r["std_structuring_fee_pct"]),
        "std_admin_fee_usd": _num(r["std_admin_fee_usd"]),
    }


def _coerce_alloc(r: dict) -> dict:
    return {
        **r,
        "commitment_amount": _num(r["commitment_amount"]),
        "price_discount_pct": _num(r["price_discount_pct"]),
        "effective_share_price": _num(r["effective_share_price"]),
        "units": _num(r["units"]),
        "contributed_amount": _num(r["contributed_amount"]),
        "outstanding_commitment": _num(r["outstanding_commitment"]),
        "mgmt_fee_pct": _num(r["mgmt_fee_pct"]),
        "performance_fee_pct": _num(r["performance_fee_pct"]),
        "structuring_fee_pct": _num(r["structuring_fee_pct"]),
        "admin_fee_usd": _num(r["admin_fee_usd"]),
        "allocation_date": _parse_date(r["allocation_date"]),
    }


def _coerce_valuation(r: dict) -> dict:
    return {
        **r,
        "valuation_date": _parse_date(r["valuation_date"]),
        "share_price": _num(r["share_price"]),
        "company_valuation_m": _num(r["company_valuation_m"]),
        "multiple_vs_entry": _num(r["multiple_vs_entry"]),
    }


def _coerce_call(r: dict) -> dict:
    return {
        **r,
        "call_date": _parse_date(r["call_date"]),
        "due_date": _parse_date(r["due_date"]),
        "amount": _num(r["amount"]),
    }


def _coerce_fee(r: dict) -> dict:
    return {
        **r,
        "fee_rate_pct": _num(r["fee_rate_pct"]),
        "amount": _num(r["amount"]),
        "due_date": _parse_date(r["due_date"]),
    }


def _coerce_dist(r: dict) -> dict:
    return {
        **r,
        "distribution_date": _parse_date(r["distribution_date"]),
        "gross_amount": _num(r["gross_amount"]),
        "performance_fee_pct": _num(r["performance_fee_pct"]),
        "performance_fee_amount": _num(r["performance_fee_amount"]),
        "net_amount": _num(r["net_amount"]),
        "fraction_of_units": _num(r["fraction_of_units"]),
    }


def _coerce_line(r: dict) -> dict:
    return {**r, "date": _parse_date(r["date"]), "amount": _num(r["amount"])}
