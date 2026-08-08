"""Deterministic financial metrics.

This is the trust boundary of the assistant. Every number an investor sees is
computed here, in plain Python, from the source rows — never by the language
model. Each public function returns both the figures and the list of source row
IDs they were derived from, so answers can be cited and audited.

All investor-facing totals are returned in the investor's reporting currency
(FX-converted via `fx.py`). Per-allocation figures are kept in deal currency
where that is what the investor actually paid/holds, and also surfaced in
reporting currency for aggregation.
"""

from __future__ import annotations

from collections import defaultdict

from .fx import convert
from .loaders import REPORT_DATE, Dataset


def _round(x: float | None, places: int = 2) -> float | None:
    return None if x is None else round(x, places)


def reporting_currency(ds: Dataset, investor_id: str) -> str:
    return ds.investors[investor_id]["reporting_currency"]


# --- allocation-level primitives -------------------------------------------


def realized_fraction(ds: Dataset, alloc: dict) -> float:
    """Share of the position already realised via distributions (0..1)."""
    dists = ds.dists_by_alloc.get(alloc["allocation_id"], [])
    frac = sum(d["fraction_of_units"] for d in dists)
    return min(frac, 1.0)


def latest_valuation(ds: Dataset, deal_id: str) -> dict | None:
    rows = ds.valuations_by_deal.get(deal_id)
    return rows[-1] if rows else None


def allocation_snapshot(ds: Dataset, alloc: dict) -> dict:
    """Everything about one position, in deal currency, with source IDs.

    current_value = remaining units x latest mark.
    Exited positions realise to 1.0 (-> 0 live value); written-off marks are 0.
    """
    deal = ds.deals[alloc["deal_id"]]
    company = ds.company_for_deal(alloc["deal_id"])
    val = latest_valuation(ds, alloc["deal_id"])
    mark_price = val["share_price"] if val else 0.0

    realized = realized_fraction(ds, alloc)
    remaining_units = alloc["units"] * (1.0 - realized)
    current_value = remaining_units * mark_price

    dists = ds.dists_by_alloc.get(alloc["allocation_id"], [])
    dist_net = sum(d["net_amount"] for d in dists)
    dist_gross = sum(d["gross_amount"] for d in dists)
    perf_fee = sum(d["performance_fee_amount"] for d in dists)

    contributed = alloc["contributed_amount"]
    # MOIC counts realised distributions (net of carry) + remaining live value
    # against capital actually contributed. Undefined when nothing contributed.
    total_value = current_value + dist_net
    moic = (total_value / contributed) if contributed else None

    sources = [alloc["allocation_id"]]
    if val:
        sources.append(val["valuation_id"])
    sources.extend(d["distribution_id"] for d in dists)

    return {
        "allocation_id": alloc["allocation_id"],
        "deal_id": alloc["deal_id"],
        "company_name": company["company_name"],
        "company_status": company["status"],
        "round": deal["round"],
        "deal_currency": alloc["deal_currency"],
        "commitment": alloc["commitment_amount"],
        "contributed": contributed,
        "outstanding_commitment": alloc["outstanding_commitment"],
        "units": alloc["units"],
        "remaining_units": _round(remaining_units, 4),
        "realized_fraction": realized,
        "entry_share_price": deal["entry_share_price"],
        "effective_share_price": alloc["effective_share_price"],
        "price_discount_pct": alloc["price_discount_pct"],
        "latest_share_price": mark_price,
        "current_value": _round(current_value),
        "distributions_gross": _round(dist_gross),
        "distributions_net": _round(dist_net),
        "performance_fee_paid": _round(perf_fee),
        "moic": _round(moic, 3),
        "allocation_status": alloc["allocation_status"],
        "sources": sources,
    }


def _to_reporting(ds: Dataset, amount: float, deal_ccy: str, investor_id: str) -> float:
    rc = reporting_currency(ds, investor_id)
    return convert(amount, deal_ccy, rc, ds.fx)


# --- portfolio overview -----------------------------------------------------


def portfolio_overview(ds: Dataset, investor_id: str) -> dict:
    rc = reporting_currency(ds, investor_id)
    allocs = ds.allocs_by_investor.get(investor_id, [])

    holdings = []
    tot_current = tot_committed = tot_contributed = tot_dist_net = 0.0
    sources: list[str] = []

    for a in allocs:
        snap = allocation_snapshot(ds, a)
        ccy = snap["deal_currency"]
        cur_rc = _to_reporting(ds, snap["current_value"], ccy, investor_id)
        committed_rc = _to_reporting(ds, snap["commitment"], ccy, investor_id)
        contributed_rc = _to_reporting(ds, snap["contributed"], ccy, investor_id)
        dist_rc = _to_reporting(ds, snap["distributions_net"], ccy, investor_id)

        tot_current += cur_rc
        tot_committed += committed_rc
        tot_contributed += contributed_rc
        tot_dist_net += dist_rc
        sources.extend(snap["sources"])

        holdings.append(
            {
                "company_name": snap["company_name"],
                "round": snap["round"],
                "allocation_id": snap["allocation_id"],
                "current_value_reporting": _round(cur_rc),
                "committed_reporting": _round(committed_rc),
                "contributed_reporting": _round(contributed_rc),
                "distributions_net_reporting": _round(dist_rc),
                "moic": snap["moic"],
                "company_status": snap["company_status"],
            }
        )

    portfolio_moic = (
        (tot_current + tot_dist_net) / tot_contributed if tot_contributed else None
    )

    return {
        "investor_id": investor_id,
        "reporting_currency": rc,
        "num_holdings": len(allocs),
        "total_current_value": _round(tot_current),
        "total_committed": _round(tot_committed),
        "total_contributed": _round(tot_contributed),
        "total_distributions_net": _round(tot_dist_net),
        "portfolio_moic": _round(portfolio_moic, 3),
        "holdings": holdings,
        "sources": sorted(set(sources)),
    }


# --- single position (aggregates a company across rounds) ------------------


def find_company(ds: Dataset, query: str) -> list[dict]:
    """Resolve a company name fragment. Returns all matches (for disambiguation)."""
    q = query.strip().lower()
    exact = [c for c in ds.companies.values() if c["company_name"].lower() == q]
    if exact:
        return exact
    return [c for c in ds.companies.values() if q in c["company_name"].lower()]


def position(ds: Dataset, investor_id: str, company_query: str) -> dict:
    rc = reporting_currency(ds, investor_id)
    matches = find_company(ds, company_query)
    if not matches:
        return {"status": "not_found", "query": company_query}
    if len(matches) > 1:
        return {
            "status": "ambiguous",
            "query": company_query,
            "candidates": [
                {"company_name": m["company_name"], "sector": m["sector"], "hq_country": m["hq_country"]}
                for m in matches
            ],
        }

    company = matches[0]
    company_deal_ids = {d["deal_id"] for d in ds.deals.values() if d["company_id"] == company["company_id"]}
    allocs = [a for a in ds.allocs_by_investor.get(investor_id, []) if a["deal_id"] in company_deal_ids]
    if not allocs:
        return {"status": "no_position", "company_name": company["company_name"]}

    rounds = []
    tot_current = tot_contributed = tot_committed = tot_dist_net = 0.0
    sources: list[str] = []
    for a in allocs:
        snap = allocation_snapshot(ds, a)
        ccy = snap["deal_currency"]
        cur_rc = _to_reporting(ds, snap["current_value"], ccy, investor_id)
        contributed_rc = _to_reporting(ds, snap["contributed"], ccy, investor_id)
        committed_rc = _to_reporting(ds, snap["commitment"], ccy, investor_id)
        dist_rc = _to_reporting(ds, snap["distributions_net"], ccy, investor_id)
        tot_current += cur_rc
        tot_contributed += contributed_rc
        tot_committed += committed_rc
        tot_dist_net += dist_rc
        sources.extend(snap["sources"])
        # Per-round figures come in TWO currencies: deal currency (what the
        # investor actually paid/holds) and reporting currency (for display and
        # aggregation). Surface both explicitly so they are never mislabelled.
        snap["reporting_currency"] = rc
        snap["current_value_reporting"] = _round(cur_rc)
        snap["contributed_reporting"] = _round(contributed_rc)
        snap["committed_reporting"] = _round(committed_rc)
        snap["distributions_net_reporting"] = _round(dist_rc)
        rounds.append(snap)

    pos_moic = (tot_current + tot_dist_net) / tot_contributed if tot_contributed else None

    return {
        "status": "ok",
        "company_name": company["company_name"],
        "sector": company["sector"],
        "company_status": company["status"],
        "reporting_currency": rc,
        "num_rounds": len(rounds),
        "rounds": rounds,
        "total_current_value": _round(tot_current),
        "total_contributed": _round(tot_contributed),
        "total_committed": _round(tot_committed),
        "total_distributions_net": _round(tot_dist_net),
        "position_moic": _round(pos_moic, 3),
        "sources": sorted(set(sources)),
    }


# --- obligations: upcoming/overdue fees and capital calls -------------------


def obligations(ds: Dataset, investor_id: str) -> dict:
    rc = reporting_currency(ds, investor_id)
    allocs = ds.allocs_by_investor.get(investor_id, [])
    alloc_ids = {a["allocation_id"] for a in allocs}

    upcoming_calls = []
    for a in allocs:
        for c in ds.calls_by_alloc.get(a["allocation_id"], []):
            if c["status"] == "Upcoming":
                amt_rc = _to_reporting(ds, c["amount"], c["currency"], investor_id)
                upcoming_calls.append(
                    {
                        "call_id": c["call_id"],
                        "company_name": ds.company_for_deal(c["deal_id"])["company_name"],
                        "call_number": c["call_number"],
                        "due_date": c["due_date"].isoformat() if c["due_date"] else None,
                        "amount": c["amount"],
                        "currency": c["currency"],
                        "amount_reporting": _round(amt_rc),
                    }
                )

    fees_due = []
    for fid_list in (ds.fees_by_alloc.get(aid, []) for aid in alloc_ids):
        for f in fid_list:
            if f["status"] in ("Upcoming", "Overdue"):
                amt_rc = _to_reporting(ds, f["amount"], f["currency"], investor_id)
                fees_due.append(
                    {
                        "fee_id": f["fee_id"],
                        "company_name": ds.company_for_deal(f["deal_id"])["company_name"],
                        "fee_type": f["fee_type"],
                        "period": f["period"],
                        "due_date": f["due_date"].isoformat() if f["due_date"] else None,
                        "status": f["status"],
                        "amount": f["amount"],
                        "currency": f["currency"],
                        "amount_reporting": _round(amt_rc),
                    }
                )

    total_calls = sum(c["amount_reporting"] for c in upcoming_calls)
    total_fees = sum(f["amount_reporting"] for f in fees_due)
    overdue_fees = [f for f in fees_due if f["status"] == "Overdue"]

    return {
        "reporting_currency": rc,
        "report_date": REPORT_DATE.isoformat(),
        "upcoming_capital_calls": sorted(upcoming_calls, key=lambda x: x["due_date"] or ""),
        "fees_due": sorted(fees_due, key=lambda x: x["due_date"] or ""),
        "total_upcoming_calls_reporting": _round(total_calls),
        "total_fees_due_reporting": _round(total_fees),
        "num_overdue_fees": len(overdue_fees),
        "sources": sorted(
            {c["call_id"] for c in upcoming_calls} | {f["fee_id"] for f in fees_due}
        ),
    }


# --- realised outcomes: distributions and exits ----------------------------


def realised_outcomes(ds: Dataset, investor_id: str) -> dict:
    rc = reporting_currency(ds, investor_id)
    allocs = ds.allocs_by_investor.get(investor_id, [])

    events = []
    tot_gross = tot_carry = tot_net = 0.0
    sources: list[str] = []
    for a in allocs:
        for d in ds.dists_by_alloc.get(a["allocation_id"], []):
            net_rc = _to_reporting(ds, d["net_amount"], d["currency"], investor_id)
            gross_rc = _to_reporting(ds, d["gross_amount"], d["currency"], investor_id)
            carry_rc = _to_reporting(ds, d["performance_fee_amount"], d["currency"], investor_id)
            tot_gross += gross_rc
            tot_carry += carry_rc
            tot_net += net_rc
            sources.append(d["distribution_id"])
            events.append(
                {
                    "distribution_id": d["distribution_id"],
                    "company_name": ds.company_for_deal(d["deal_id"])["company_name"],
                    "type": d["distribution_type"],
                    "date": d["distribution_date"].isoformat() if d["distribution_date"] else None,
                    "fraction_of_units": d["fraction_of_units"],
                    "gross": d["gross_amount"],
                    "performance_fee_pct": d["performance_fee_pct"],
                    "performance_fee_amount": d["performance_fee_amount"],
                    "net": d["net_amount"],
                    "currency": d["currency"],
                    "net_reporting": _round(net_rc),
                }
            )

    return {
        "reporting_currency": rc,
        "num_events": len(events),
        "events": sorted(events, key=lambda x: x["date"] or ""),
        "total_gross_reporting": _round(tot_gross),
        "total_carry_reporting": _round(tot_carry),
        "total_net_reporting": _round(tot_net),
        "sources": sorted(set(sources)),
    }


# --- fees on a deal: effective vs standard schedule ------------------------


def fees_breakdown(ds: Dataset, investor_id: str, company_query: str) -> dict:
    matches = find_company(ds, company_query)
    if not matches:
        return {"status": "not_found", "query": company_query}
    if len(matches) > 1:
        return {
            "status": "ambiguous",
            "query": company_query,
            "candidates": [{"company_name": m["company_name"], "sector": m["sector"]} for m in matches],
        }
    company = matches[0]
    deal_ids = {d["deal_id"] for d in ds.deals.values() if d["company_id"] == company["company_id"]}
    allocs = [a for a in ds.allocs_by_investor.get(investor_id, []) if a["deal_id"] in deal_ids]
    if not allocs:
        return {"status": "no_position", "company_name": company["company_name"]}

    rounds = []
    for a in allocs:
        deal = ds.deals[a["deal_id"]]
        charged = [
            {
                "fee_id": f["fee_id"],
                "fee_type": f["fee_type"],
                "period": f["period"],
                "rate_pct": f["fee_rate_pct"],
                "basis": f["basis"],
                "amount": f["amount"],
                "currency": f["currency"],
                "status": f["status"],
            }
            for f in ds.fees_by_alloc.get(a["allocation_id"], [])
        ]
        rounds.append(
            {
                "allocation_id": a["allocation_id"],
                "round": deal["round"],
                "deal_currency": a["deal_currency"],
                "fee_discount_flag": a["fee_discount"],
                "effective": {
                    "mgmt_fee_pct": a["mgmt_fee_pct"],
                    "performance_fee_pct": a["performance_fee_pct"],
                    "structuring_fee_pct": a["structuring_fee_pct"],
                    "admin_fee_usd": a["admin_fee_usd"],
                },
                "deal_standard": {
                    "std_mgmt_fee_pct": deal["std_mgmt_fee_pct"],
                    "std_performance_fee_pct": deal["std_performance_fee_pct"],
                    "std_structuring_fee_pct": deal["std_structuring_fee_pct"],
                    "std_admin_fee_usd": deal["std_admin_fee_usd"],
                },
                "charged_fees": charged,
                "sources": [a["allocation_id"], a["deal_id"]] + [c["fee_id"] for c in charged],
            }
        )

    return {
        "status": "ok",
        "company_name": company["company_name"],
        "rounds": rounds,
        "sources": sorted({s for r in rounds for s in r["sources"]}),
    }


# --- valuation history of a company, and its effect on the investor --------


def valuation_history(ds: Dataset, investor_id: str, company_query: str) -> dict:
    matches = find_company(ds, company_query)
    if not matches:
        return {"status": "not_found", "query": company_query}
    if len(matches) > 1:
        return {
            "status": "ambiguous",
            "query": company_query,
            "candidates": [{"company_name": m["company_name"], "sector": m["sector"]} for m in matches],
        }
    company = matches[0]
    deals = [d for d in ds.deals.values() if d["company_id"] == company["company_id"]]
    investor_deal_ids = {a["deal_id"] for a in ds.allocs_by_investor.get(investor_id, [])}

    series = []
    for deal in sorted(deals, key=lambda d: d["deal_date"] or REPORT_DATE):
        marks = [
            {
                "valuation_id": v["valuation_id"],
                "date": v["valuation_date"].isoformat() if v["valuation_date"] else None,
                "share_price": v["share_price"],
                "company_valuation_m": v["company_valuation_m"],
                "mark_source": v["mark_source"],
                "multiple_vs_entry": v["multiple_vs_entry"],
            }
            for v in ds.valuations_by_deal.get(deal["deal_id"], [])
        ]
        # Per-round MOIC contribution for this investor, if they hold this round.
        round_snap = None
        for a in ds.allocs_by_investor.get(investor_id, []):
            if a["deal_id"] == deal["deal_id"]:
                round_snap = allocation_snapshot(ds, a)
                break
        series.append(
            {
                "deal_id": deal["deal_id"],
                "round": deal["round"],
                "entry_share_price": deal["entry_share_price"],
                "marks": marks,
                "investor_holds": deal["deal_id"] in investor_deal_ids,
                "investor_moic": round_snap["moic"] if round_snap else None,
                "investor_effective_share_price": round_snap["effective_share_price"] if round_snap else None,
            }
        )

    return {
        "status": "ok",
        "company_name": company["company_name"],
        "company_status": company["status"],
        "rounds": series,
        "sources": sorted({m["valuation_id"] for r in series for m in r["marks"]}),
    }


# --- account statement (plain-language inputs) -----------------------------


def account_statement(ds: Dataset, investor_id: str) -> dict:
    rc = reporting_currency(ds, investor_id)
    lines = ds.statement_by_investor.get(investor_id, [])

    by_type: dict[str, float] = defaultdict(float)
    detail = []
    for ln in lines:
        amt_rc = convert(ln["amount"], ln["currency"], rc, ds.fx)
        by_type[ln["type"]] += amt_rc
        detail.append(
            {
                "line_id": ln["line_id"],
                "date": ln["date"].isoformat() if ln["date"] else None,
                "type": ln["type"],
                "company_name": ds.company_for_deal(ln["deal_id"])["company_name"],
                "amount": ln["amount"],
                "currency": ln["currency"],
                "amount_reporting": _round(amt_rc),
                "reference_id": ln["reference_id"],
            }
        )

    net = sum(by_type.values())
    return {
        "reporting_currency": rc,
        "summary_by_type": {k: _round(v) for k, v in sorted(by_type.items())},
        "net_position_reporting": _round(net),
        "num_lines": len(lines),
        "lines": detail,
        "sources": [ln["line_id"] for ln in lines],
    }
