"""Offline deterministic report — no API key required.

Prints the grounded figures (and their source row IDs) for an investor, so the
numbers can be verified independently of the language model.

    python -m src.report --investor INV001
"""

from __future__ import annotations

import argparse
import json

from . import metrics
from .loaders import load_dataset
from .personalize import investor_signals


def _money(x: float | None) -> str:
    """Thousands-separated, 2-decimal display. '—' for missing values."""
    return "—" if x is None else f"{x:,.2f}"


def _mult(x: float | None) -> str:
    return "—" if x is None else f"{x:.3f}x"


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic investor report (no LLM)")
    parser.add_argument("--investor", default="INV001")
    parser.add_argument("--json", action="store_true", help="Emit raw JSON instead of a summary.")
    args = parser.parse_args()

    ds = load_dataset()
    if args.investor not in ds.investors:
        print(f"Unknown investor_id: {args.investor}")
        return 1

    iid = args.investor
    signals = investor_signals(ds, iid)
    overview = metrics.portfolio_overview(ds, iid)
    obligations = metrics.obligations(ds, iid)
    realised = metrics.realised_outcomes(ds, iid)
    statement = metrics.account_statement(ds, iid)

    if args.json:
        print(json.dumps(
            {"signals": signals, "overview": overview, "obligations": obligations,
             "realised": realised, "statement": statement},
            indent=2, default=str,
        ))
        return 0

    rc = overview["reporting_currency"]
    print(f"== {signals['name']} ({iid}) — reporting in {rc} ==")
    print(f"profile: type={signals['investor_type']} age={signals['age']} "
          f"tech={signals['tech_savviness']} deals={signals['num_deals']} "
          f"top_sectors={signals['top_sectors']}")
    print()
    print(f"Holdings: {overview['num_holdings']}")
    print(f"Current value:   {_money(overview['total_current_value'])} {rc}")
    print(f"Committed:       {_money(overview['total_committed'])} {rc}")
    print(f"Contributed:     {_money(overview['total_contributed'])} {rc}")
    print(f"Distributions:   {_money(overview['total_distributions_net'])} {rc} (net of carry)")
    print(f"Portfolio MOIC:  {_mult(overview['portfolio_moic'])}")
    print()
    name_w = max((len(f"{h['company_name']} {h['round']}") for h in overview["holdings"]), default=0)
    for h in overview["holdings"]:
        label = f"{h['company_name']} {h['round']}"
        print(f"  - {label:<{name_w}}  value={_money(h['current_value_reporting']):>14} {rc}"
              f"  contributed={_money(h['contributed_reporting']):>14} {rc}"
              f"  MOIC={_mult(h['moic']):>8}  [{h['company_status']}] ({h['allocation_id']})")
    print()
    print(f"Upcoming capital calls: {_money(obligations['total_upcoming_calls_reporting'])} {rc}, "
          f"fees due: {_money(obligations['total_fees_due_reporting'])} {rc}, "
          f"overdue fees: {obligations['num_overdue_fees']}")
    print(f"Realised (net of carry): {_money(realised['total_net_reporting'])} {rc} "
          f"across {realised['num_events']} event(s)")
    print(f"Statement net position: {_money(statement['net_position_reporting'])} {rc} "
          f"over {statement['num_lines']} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
