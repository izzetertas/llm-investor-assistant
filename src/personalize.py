"""Personalisation signals.

Derives the profile signals the assistant uses to adapt *tone, depth, and
framing* — never the numbers. Some signals are stored on the investor row
(age, tech_savviness); others are derived from their allocations (how many
deals, which sectors). The output is a short directive injected into the
system prompt.
"""

from __future__ import annotations

from collections import Counter

from .loaders import Dataset


def investor_signals(ds: Dataset, investor_id: str) -> dict:
    inv = ds.investors[investor_id]
    allocs = ds.allocs_by_investor.get(investor_id, [])
    active = [a for a in allocs if a["allocation_status"] == "Active"]

    sectors = Counter()
    companies = set()
    for a in allocs:
        company = ds.company_for_deal(a["deal_id"])
        sectors[company["sector"]] += 1
        companies.add(company["company_id"])

    top_sectors = [s for s, _ in sectors.most_common(3)]

    return {
        "investor_id": investor_id,
        "name": inv["investor_name"],
        "investor_type": inv["investor_type"],
        "reporting_currency": inv["reporting_currency"],
        "age": inv["age"],
        "tech_savviness": inv["tech_savviness"],
        "kyc_status": inv["kyc_status"],
        "num_deals": len(active),
        "num_companies": len(companies),
        "top_sectors": top_sectors,
        "has_holdings": len(allocs) > 0,
    }


def personalisation_directive(signals: dict) -> str:
    """Turn signals into a concise tone/depth instruction for the system prompt.

    The directive only governs how the answer is phrased. The figures are
    produced by the deterministic tools and are identical for every investor.
    """
    tech = (signals.get("tech_savviness") or "Medium").lower()
    age = signals.get("age")
    num_deals = signals.get("num_deals", 0)

    lines = [
        f"You are serving {signals['name']} (investor type: {signals['investor_type']}, "
        f"reporting currency: {signals['reporting_currency']}).",
    ]

    # Depth / jargon based on tech-savviness and (for individuals) age.
    plain = tech == "low" or (isinstance(age, (int, float)) and age >= 65)
    if plain:
        lines.append(
            "Use plain language and keep answers short. Briefly explain any "
            "finance jargon the first time it appears (e.g. MOIC = how many times "
            "your money has grown; carry = the performance fee the manager takes). "
            "Avoid dense tables; lead with the single number that answers the question."
        )
    elif tech == "high":
        many = " active in many deals" if num_deals >= 5 else ""
        lines.append(
            f"This is a sophisticated investor{many}. Be concise and data-dense; "
            "assume fluency with MOIC, carry, capital calls, and FX. Skip "
            "definitions and preamble; lead with the figures."
        )
    else:
        lines.append(
            "Use clear, professional language. Define a term only if it is "
            "non-obvious. Keep it focused and lead with the key figure."
        )

    # Portfolio-shape framing.
    if signals.get("top_sectors"):
        lines.append(
            "Where relevant, reflect the investor's portfolio shape — their most "
            f"active sectors are {', '.join(signals['top_sectors'])} across "
            f"{signals['num_deals']} active deal(s) — rather than answering generically."
        )

    if not signals.get("has_holdings"):
        lines.append(
            "This investor currently holds no positions. If they ask about their "
            "portfolio, say plainly that they have no investments yet and offer to "
            "explain what they would see once they do."
        )

    lines.append("Stay professional and never patronising. Never alter or round the numbers the tools return.")
    return "\n".join(lines)
