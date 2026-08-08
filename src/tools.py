"""Tool schemas and investor-bound dispatch.

Two halves, kept separate on purpose:

  * TOOL_SCHEMAS  — the JSON the model sees (names, descriptions, arg schemas).
  * build_dispatch — binds the schemas to the *pure* metric functions and to a
    single investor_id, returning a name -> callable map.

The investor_id is captured in a closure, never exposed as a tool argument, so
the model has no way to request another investor's data. The same pure
functions could be re-exposed over MCP later without touching metrics.py.
"""

from __future__ import annotations

from typing import Callable

from . import metrics
from .loaders import Dataset

# Schemas sent to the model. Order is stable so the tool prefix stays cacheable.
TOOL_SCHEMAS: list[dict] = [
    {
        "name": "get_portfolio_overview",
        "description": (
            "The investor's whole-portfolio summary: number of holdings, total "
            "current value, total committed vs contributed, total distributions, "
            "and overall MOIC — all in their reporting currency, plus a per-holding "
            "breakdown. Use for 'how am I doing', 'what's my portfolio worth', "
            "'what's my MOIC', 'committed vs contributed'."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_position",
        "description": (
            "The investor's position in ONE company, aggregated across every round "
            "they hold (e.g. Forgecraft Seed + Series A + Series B). Returns current "
            "value, cost basis, the effective share price they paid per round, "
            "distributions, and MOIC. Use for questions about a specific company. "
            "If the name is ambiguous (e.g. 'Northpeak') the tool returns the "
            "candidates to disambiguate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string", "description": "Company name or fragment, e.g. 'Forgecraft'."}
            },
            "required": ["company"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_obligations",
        "description": (
            "Upcoming capital calls and upcoming/overdue management & admin fees, "
            "with due dates and amounts in the reporting currency. Use for 'what do "
            "I owe', 'any capital calls coming up', 'do I have overdue fees'."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_realised_outcomes",
        "description": (
            "Realised distributions and exits: exit proceeds and secondary sales, "
            "gross, the performance fee (carry) withheld, and the net the investor "
            "actually received. Use for 'what have I cashed out', 'exits', "
            "'distributions', 'what did I get after carry'."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_fees",
        "description": (
            "Fee breakdown for the investor's allocation(s) in ONE company: their "
            "EFFECTIVE mgmt/performance/structuring/admin rates compared against the "
            "deal's STANDARD schedule, the fee_discount flag, and the individual fee "
            "rows charged. Use for 'what fees am I paying on X', 'did I get a discount'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"company": {"type": "string", "description": "Company name or fragment."}},
            "required": ["company"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_valuation_history",
        "description": (
            "How a company's valuation/share price has moved over time across its "
            "rounds (markups, internal marks, exits, write-offs, down rounds), and "
            "the investor's per-round MOIC where they hold it. Use for 'how has X's "
            "valuation changed', 'did X have a down round', 'what did that do to my MOIC'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"company": {"type": "string", "description": "Company name or fragment."}},
            "required": ["company"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_account_statement",
        "description": (
            "Plain-language account statement: capital contributions, fees, and "
            "distributions, summarised by type and netted, in the reporting currency, "
            "with the underlying signed statement lines. Use for 'give me my "
            "statement', 'summary of my cash in and out'."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def build_dispatch(ds: Dataset, investor_id: str) -> dict[str, Callable[..., dict]]:
    """Bind each tool name to a callable scoped to this investor."""
    return {
        "get_portfolio_overview": lambda: metrics.portfolio_overview(ds, investor_id),
        "get_position": lambda company: metrics.position(ds, investor_id, company),
        "get_obligations": lambda: metrics.obligations(ds, investor_id),
        "get_realised_outcomes": lambda: metrics.realised_outcomes(ds, investor_id),
        "get_fees": lambda company: metrics.fees_breakdown(ds, investor_id, company),
        "get_valuation_history": lambda company: metrics.valuation_history(ds, investor_id, company),
        "get_account_statement": lambda: metrics.account_statement(ds, investor_id),
    }
