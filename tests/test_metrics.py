"""Edge-case and invariant tests for the deterministic layer.

These assert the dataset's deliberate trap cases behave correctly and that the
core relationships (MOIC, FX, source citations, investor isolation) hold. They
need no API key — only the CSVs.
"""

from __future__ import annotations

import pytest

from src import metrics
from src.fx import convert
from src.loaders import load_dataset
from src.tools import build_dispatch

ds = load_dataset()


def _allocs_for_deal(deal_id: str) -> list[dict]:
    return [a for a in ds.allocations if a["deal_id"] == deal_id]


def _investors_with_no_holdings() -> list[str]:
    return [iid for iid in ds.investors if not ds.allocs_by_investor.get(iid)]


# --- FX -------------------------------------------------------------------


def test_fx_via_usd():
    # GBP->USD direct
    assert convert(100, "GBP", "USD", ds.fx) == pytest.approx(135.0)
    # USD->GBP
    assert convert(135, "USD", "GBP", ds.fx) == pytest.approx(100.0)
    # EUR->GBP must route via USD: 100 EUR -> 109 USD -> /1.35 GBP
    assert convert(100, "EUR", "GBP", ds.fx) == pytest.approx(109.0 / 1.35)
    assert convert(50, "USD", "USD", ds.fx) == 50


# --- trap: exit (Helianthe, CO004 / DEAL007) ------------------------------


def test_exit_has_zero_live_value_but_realised_distributions():
    deal_id = "DEAL007"  # Helianthe Series A, Exited
    allocs = _allocs_for_deal(deal_id)
    assert allocs, "expected allocations in the exited deal"
    for a in allocs:
        snap = metrics.allocation_snapshot(ds, a)
        assert snap["current_value"] == 0, "exited round should have no live value"
    # At least one investor in this deal has net distributions, and MOIC counts them.
    inv = allocs[0]["investor_id"]
    realised = metrics.realised_outcomes(ds, inv)
    assert realised["total_net_reporting"] > 0
    pos = metrics.position(ds, inv, "Helianthe")
    assert pos["status"] == "ok"
    assert pos["total_current_value"] == 0
    assert pos["total_distributions_net"] > 0
    assert pos["position_moic"] is not None  # MOIC defined and driven by distributions


# --- trap: write-off (Yappio, CO005 / DEAL008) ----------------------------


def test_writeoff_shows_zero_value_and_a_loss():
    allocs = _allocs_for_deal("DEAL008")
    assert allocs
    for a in allocs:
        snap = metrics.allocation_snapshot(ds, a)
        assert snap["current_value"] == 0
        if snap["contributed"] and not snap["distributions_net"]:
            assert snap["moic"] == 0  # total loss, no distributions


# --- trap: partial secondary (Tallybook, DEAL020, 30% sold) ---------------


def test_partial_secondary_splits_realised_and_live():
    # ALC0520 (INV013) sold 30% in a secondary; 70% still marked live.
    alloc = next(a for a in ds.allocations if a["allocation_id"] == "ALC0520")
    snap = metrics.allocation_snapshot(ds, alloc)
    assert snap["realized_fraction"] == pytest.approx(0.3)
    assert snap["remaining_units"] == pytest.approx(snap["units"] * 0.7)
    assert snap["distributions_net"] > 0
    assert snap["current_value"] > 0  # remaining 70% still has value


# --- trap: pending / unfunded commitment ----------------------------------


def test_pending_allocation_is_not_deployed_capital():
    pending = [a for a in ds.allocations if a["allocation_status"] == "Pending"]
    assert pending, "dataset should contain a pending allocation"
    for a in pending:
        snap = metrics.allocation_snapshot(ds, a)
        assert snap["contributed"] == 0
        assert snap["moic"] is None  # undefined, not zero


# --- trap: zero-holding investor ------------------------------------------


def test_zero_holding_investor():
    empties = _investors_with_no_holdings()
    assert len(empties) >= 1
    ov = metrics.portfolio_overview(ds, empties[0])
    assert ov["num_holdings"] == 0
    assert ov["total_current_value"] == 0
    assert ov["portfolio_moic"] is None


# --- trap: similar names (Northpeak Analytics vs Health) -------------------


def test_similar_names_disambiguate():
    matches = metrics.find_company(ds, "Northpeak")
    assert len(matches) == 2
    # position should refuse to guess and return candidates
    any_inv = next(iter(ds.investors))
    res = metrics.position(ds, any_inv, "Northpeak")
    assert res["status"] == "ambiguous"
    assert len(res["candidates"]) == 2
    # exact name resolves cleanly
    exact = metrics.find_company(ds, "Northpeak Health")
    assert len(exact) == 1 and exact[0]["company_name"] == "Northpeak Health"


# --- trap: same company across multiple rounds (Forgecraft) ----------------


def test_multi_round_position_aggregates():
    # Forgecraft has 3 rounds; INV001 holds at least the Seed (ALC0001).
    pos = metrics.position(ds, "INV001", "Forgecraft")
    assert pos["status"] == "ok"
    assert pos["num_rounds"] >= 1
    # aggregate equals the sum of per-round reporting-currency values
    parts = sum(
        convert(r["current_value"], r["deal_currency"], pos["reporting_currency"], ds.fx)
        for r in pos["rounds"]
    )
    assert pos["total_current_value"] == pytest.approx(parts, rel=1e-6)


# --- fees: effective vs standard ------------------------------------------


def test_fee_discount_flag_matches_effective_rates():
    # Find an allocation flagged with a discount and confirm an effective rate
    # is genuinely below the deal standard.
    discounted = [a for a in ds.allocations if a["fee_discount"] == "Yes"]
    assert discounted
    a = discounted[0]
    deal = ds.deals[a["deal_id"]]
    below = (
        a["mgmt_fee_pct"] < deal["std_mgmt_fee_pct"]
        or a["performance_fee_pct"] < deal["std_performance_fee_pct"]
        or a["structuring_fee_pct"] < deal["std_structuring_fee_pct"]
        or a["admin_fee_usd"] < deal["std_admin_fee_usd"]
    )
    assert below, "fee_discount=Yes but no effective rate is below standard"

    # And a non-discounted allocation should have effective == standard fees.
    full = next(a for a in ds.allocations if a["fee_discount"] == "No")
    deal = ds.deals[full["deal_id"]]
    assert full["mgmt_fee_pct"] == deal["std_mgmt_fee_pct"]


# --- citations: every answer carries source rows --------------------------


def test_metrics_return_sources():
    iid = "INV001"
    assert metrics.portfolio_overview(ds, iid)["sources"]
    assert metrics.account_statement(ds, iid)["sources"]
    pos = metrics.position(ds, iid, "Forgecraft")
    assert pos["sources"]


# --- security: dispatch is bound to one investor --------------------------


def test_dispatch_is_investor_scoped():
    iid = "INV001"
    dispatch = build_dispatch(ds, iid)
    ov = dispatch["get_portfolio_overview"]()
    owned = {a["allocation_id"] for a in ds.allocs_by_investor.get(iid, [])}
    for h in ov["holdings"]:
        assert h["allocation_id"] in owned, "overview leaked another investor's allocation"


# --- MOIC relationship holds ----------------------------------------------


def test_moic_definition():
    for a in ds.allocations:
        snap = metrics.allocation_snapshot(ds, a)
        if snap["contributed"]:
            expected = round(
                (snap["current_value"] + snap["distributions_net"]) / snap["contributed"], 3
            )
            assert snap["moic"] == expected
        else:
            assert snap["moic"] is None
