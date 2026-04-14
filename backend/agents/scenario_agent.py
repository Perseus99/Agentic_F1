"""
Scenario Agent — reads market snapshot + business financials and proposes
2-3 ranked simulation scenarios for the business owner to choose from.

Rather than making the user pick a use case from a menu, the agent:
1. Calls get_business_signals to understand the current business state
2. Calls get_market_signals to understand the economic environment
3. Calls propose_scenario (1-3 times) to record each ranked suggestion
4. Returns the accumulated scenarios as structured objects

Each scenario is a fully-formed simulation request — the frontend can pass
the params directly to POST /api/simulate without any transformation.

Falls back to one default scenario per use case if the agent fails.
"""
from __future__ import annotations

import json
import sys
import os

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from agents.base import run_agent

# ── Tools ─────────────────────────────────────────────────────────────────────

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_business_signals",
            "description": (
                "Returns the current financial state of the business: "
                "monthly revenue, margin, costs, employee count, and cash balance."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_signals",
            "description": (
                "Returns key economic signals from the market snapshot: "
                "CPI trend, unemployment, sector growth rate, market sentiment, "
                "labor elasticity, and market saturation."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_scenario",
            "description": (
                "Record one proposed simulation scenario. Call this 2-3 times "
                "to propose a ranked set of options for the business owner. "
                "Only fill in the param fields that apply to the chosen use_case."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "rank": {
                        "type": "integer",
                        "description": "1 = best recommendation, 2 = second best, 3 = third",
                    },
                    "use_case": {
                        "type": "string",
                        "enum": ["pricing", "audience", "franchising"],
                        "description": "Which simulation type this scenario uses",
                    },
                    "label": {
                        "type": "string",
                        "description": "Short title for this scenario (max 8 words)",
                    },
                    "rationale": {
                        "type": "string",
                        "description": (
                            "1-2 sentences explaining why this scenario is worth "
                            "simulating given the business and market context"
                        ),
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "How confident you are this is a good option to explore",
                    },
                    "timeline_months": {
                        "type": "integer",
                        "description": "Forecast horizon in months (use 6 or 12)",
                    },
                    # --- pricing params ---
                    "price_change_pct": {
                        "type": "integer",
                        "description": "pricing only: percentage to change price, e.g. 8 means +8%",
                    },
                    # --- audience params ---
                    "audience_shift": {
                        "type": "string",
                        "enum": ["18_34", "35_54", "55_plus"],
                        "description": "audience only: target demographic segment",
                    },
                    "marketing_budget_pct": {
                        "type": "integer",
                        "description": "audience only: marketing budget as % of revenue, e.g. 8",
                    },
                    # --- franchising params ---
                    "new_locations": {
                        "type": "integer",
                        "description": "franchising only: number of new locations to open",
                    },
                    "franchise_fee": {
                        "type": "integer",
                        "description": "franchising only: investment per location in dollars",
                    },
                    "royalty_pct": {
                        "type": "integer",
                        "description": "franchising only: royalty percentage, e.g. 5 means 5%",
                    },
                },
                "required": ["rank", "use_case", "label", "rationale", "confidence", "timeline_months"],
            },
        },
    },
]

_SYSTEM = """You are a business strategy advisor for small businesses.

Your job: analyse the business's financial position and local economic environment,
then propose exactly 2 or 3 simulation scenarios — ranked from best to worst.

REQUIRED workflow — follow this exactly:
1. Call get_business_signals
2. Call get_market_signals
3. Call propose_scenario with rank=1 (your top recommendation)
4. Call propose_scenario with rank=2 (second option, different use_case from rank 1)
5. Optionally call propose_scenario with rank=3 if there is a third worthwhile option
6. Write one sentence summarising your top recommendation

Rules for scenarios:
- Rank 1 MUST be the most actionable given the market signals
- Use different use_cases across your proposals (pricing / audience / franchising)
- Always include at least one pricing scenario
- Be specific with numeric parameters, not vague ranges
- Do not recommend franchising if margin is below 15%
- Do not recommend a price increase above 12% when CPI trend is rising
- Use conservative parameters when market signals are negative or mixed
- timeline_months should be 6 for pricing/audience, 12 for franchising"""


# ── Tool implementations (closures over ip1/ms) ───────────────────────────────

def _make_tool_fns(ip1: dict, ms: dict) -> tuple[list[dict], dict]:
    """Build the tool function closures and accumulated scenarios list."""
    scenarios: list[dict] = []

    def get_business_signals() -> dict:
        revenue  = float(ip1.get("monthly_revenue", 0))
        costs    = float(ip1.get("monthly_costs", 0))
        margin   = round((revenue - costs) / revenue, 4) if revenue > 0 else 0.0
        return {
            "monthly_revenue":  revenue,
            "monthly_costs":    costs,
            "gross_margin":     margin,
            "employee_count":   ip1.get("employee_count", 0),
            "avg_price_point":  ip1.get("avg_price_point", 0),
        }

    def get_market_signals() -> dict:
        econ   = ms.get("economic_indicators", {})
        news   = ms.get("news_context", {})
        elast  = ms.get("elasticity_modifiers", {})
        market = ms.get("market_data", {})
        return {
            "cpi_trend":          econ.get("cpi", {}).get("trend", "stable"),
            "unemployment_trend": econ.get("unemployment", {}).get("trend", "stable"),
            "sector_growth_rate": econ.get("sector_growth_rate", {}).get("current", 0.0),
            "sector_trend":       econ.get("sector_consumer_spending", {}).get("trend", "stable"),
            "market_sentiment":   float(news.get("sentiment_score", 0.0)),
            "labor_elasticity":   float(elast.get("labor_elasticity", 1.0)),
            "market_saturation":  float(market.get("market_saturation_index", 0.5)),
        }

    def propose_scenario(
        rank:                int,
        use_case:            str,
        label:               str,
        rationale:           str,
        confidence:          str,
        timeline_months:     int  = 6,
        # pricing
        price_change_pct:    int  = None,
        # audience
        audience_shift:      str  = None,
        marketing_budget_pct: int = None,
        # franchising
        new_locations:       int  = None,
        franchise_fee:       int  = None,
        royalty_pct:         int  = None,
    ) -> dict:
        # Reconstruct the nested params dict from flat fields
        if use_case == "pricing":
            params = {
                "priceChangePct":  price_change_pct if price_change_pct is not None else 5,
                "timelineMonths":  timeline_months,
            }
        elif use_case == "audience":
            params = {
                "audienceShift":      audience_shift or "35_54",
                "marketingBudgetPct": marketing_budget_pct if marketing_budget_pct is not None else 8,
                "timelineMonths":     timeline_months,
            }
        else:  # franchising
            params = {
                "newLocations":  new_locations if new_locations is not None else 1,
                "franchiseFee":  franchise_fee if franchise_fee is not None else 45000,
                "royaltyPct":    royalty_pct if royalty_pct is not None else 5,
                "timelineMonths": timeline_months,
            }

        scenario = {
            "rank":       rank,
            "use_case":   use_case,
            "label":      label,
            "rationale":  rationale,
            "confidence": confidence,
            "params":     params,
        }
        scenarios.append(scenario)
        print(f"[scenario_agent] Scenario #{rank} ({use_case}): {label}")
        return {"recorded": True, "total_scenarios": len(scenarios)}

    tool_fns = {
        "get_business_signals": get_business_signals,
        "get_market_signals":   get_market_signals,
        "propose_scenario":     propose_scenario,
    }
    return scenarios, tool_fns


# ── Fallback scenarios ────────────────────────────────────────────────────────

def _fallback_scenarios(ip1: dict, ms: dict) -> list[dict]:
    """
    One generic scenario per use case — returned if the agent fails.
    Parameters are conservative defaults appropriate for any business.
    """
    econ        = ms.get("economic_indicators", {})
    cpi_trend   = econ.get("cpi", {}).get("trend", "stable")
    revenue     = float(ip1.get("monthly_revenue", 0))
    costs       = float(ip1.get("monthly_costs", 0))
    margin      = (revenue - costs) / revenue if revenue > 0 else 0.0

    # Conservative price change: 5% normally, 3% if CPI is rising
    price_pct = 3 if cpi_trend == "rising" else 5

    scenarios = [
        {
            "rank": 1, "use_case": "pricing",
            "label": f"Modest {price_pct}% price adjustment",
            "rationale": "A conservative price test to assess customer sensitivity.",
            "confidence": "medium",
            "params": {"priceChangePct": price_pct, "timelineMonths": 6},
        },
        {
            "rank": 2, "use_case": "audience",
            "label": "Shift marketing to 35-54 demographic",
            "rationale": "Middle-income demographic with stable purchasing behaviour.",
            "confidence": "medium",
            "params": {"audienceShift": "35_54", "marketingBudgetPct": 8, "timelineMonths": 6},
        },
    ]

    # Only suggest franchising if margin looks viable
    if margin >= 0.15:
        scenarios.append({
            "rank": 3, "use_case": "franchising",
            "label": "Explore second location",
            "rationale": "Margin supports expansion; model the investment payback.",
            "confidence": "low",
            "params": {"newLocations": 1, "franchiseFee": 45000,
                       "royaltyPct": 5, "timelineMonths": 12},
        })

    return scenarios


# ── Entry point ───────────────────────────────────────────────────────────────

def suggest_scenarios(ip1: dict, ms: dict, business_name: str = "the business") -> list[dict]:
    """
    Scenario Agent entry point.

    Args:
        ip1:           current-state business financials (from twin_layer_to_ip1)
        ms:            market snapshot (from build_market_snapshot)
        business_name: for logging only

    Returns:
        List of scenario dicts sorted by rank, each with:
            {rank, use_case, label, rationale, confidence, params}
        params keys match the frontend sim form fields exactly.
    """
    print(f"[scenario_agent] Proposing scenarios for '{business_name}'...")

    econ   = ms.get("economic_indicators", {})
    news   = ms.get("news_context", {})
    elast  = ms.get("elasticity_modifiers", {})
    revenue = float(ip1.get("monthly_revenue", 0))
    costs   = float(ip1.get("monthly_costs", 0))
    margin  = round((revenue - costs) / revenue, 4) if revenue > 0 else 0.0

    user_message = (
        f"Business: {business_name}\n"
        f"  Monthly revenue: ${revenue:,.0f}\n"
        f"  Gross margin: {margin*100:.1f}%\n"
        f"  Employees: {ip1.get('employee_count', 0)}\n\n"
        "Call get_business_signals and get_market_signals first, "
        "then call propose_scenario 2-3 times (ranked 1 best → 3 worst)."
    )

    scenarios, tool_fns = _make_tool_fns(ip1, ms)

    try:
        run_agent(
            system_prompt=_SYSTEM,
            user_message=user_message,
            tools=_TOOLS,
            tool_functions=tool_fns,
            max_iterations=8,
        )
    except Exception as e:
        print(f"[scenario_agent] Agent failed ({e}) — using fallback scenarios")
        return _fallback_scenarios(ip1, ms)

    if not scenarios:
        print("[scenario_agent] No scenarios proposed — using fallback")
        return _fallback_scenarios(ip1, ms)

    # Sort by rank, deduplicate use_cases (keep highest-ranked per use_case)
    scenarios.sort(key=lambda s: s.get("rank", 99))
    seen_use_cases: set[str] = set()
    deduped = []
    for s in scenarios:
        uc = s.get("use_case", "")
        if uc not in seen_use_cases:
            deduped.append(s)
            seen_use_cases.add(uc)

    print(f"[scenario_agent] Returning {len(deduped)} scenario(s)")
    return deduped
