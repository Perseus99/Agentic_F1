"""
TwinTrack — Simulation Layer
================================
Input:  MS  (market snapshot: economic indicators + Prophet forecasts + sentiment)
        IP1 (business financials: current state)
        IP2 (decision being simulated: use case + parameters)

Output: OP1 (base case — control, no change applied)
        OP2 (experiment — decision applied, modifiers layered on top)

Decision approach
-----------------
- ALL calculations are rules-based / formula-driven.  No LLM calls here.
- Prophet forecast values are READ from MS.forecasts (computed in ML layer).
- Sentiment is READ from MS.news_context.sentiment_score (computed by LLM in ML layer).
- Elasticity modifiers are READ from MS.elasticity_modifiers (computed in ML layer).
- The Sim layer's only job: apply economic formulas and produce OP1 + OP2.
"""

from __future__ import annotations
import json
import os
from datetime import date
from typing import Any

_SIM_DIR  = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.normpath(os.path.join(_SIM_DIR, "..", "data"))
OP_DIR    = os.path.join(_DATA_DIR, "op")


# ── Confidence Score ──────────────────────────────────────────────────────────

# For each use case, which direction of each indicator is "favorable" to the business.
# Favorable trend → higher stability score → higher confidence.
_FAVORABLE: dict[str, dict[str, str]] = {
    "pricing": {
        "cpi":                    "stable",   # rising CPI hurts consumer willingness to pay
        "unemployment":           "falling",  # falling unemployment → more disposable income
        "gdp":                    "rising",   # growing economy → more spending
        "sector_consumer_spending": "rising",
        "interest_rate":          "falling",  # lower rates → more business investment possible
    },
    "target_audience": {
        "cpi":                    "stable",
        "unemployment":           "falling",
        "gdp":                    "rising",
        "sector_consumer_spending": "rising",
        "interest_rate":          "stable",
    },
    "franchising": {
        "cpi":                    "stable",
        "unemployment":           "stable",   # stable labor pool
        "gdp":                    "rising",
        "sector_consumer_spending": "rising",
        "interest_rate":          "falling",  # lower rates reduce capital cost
    },
}

_TREND_SCORES = {
    "stable":       0.85,
    "favorable":    0.70,
    "unfavorable":  0.30,
}


def _trend_stability(trend: str, indicator: str, use_case: str) -> float:
    """
    Rule: stable → 0.85, moving in favorable direction → 0.70,
    moving against business → 0.30.
    """
    favorable = _FAVORABLE.get(use_case, {}).get(indicator, "stable")
    if trend == "stable":
        return _TREND_SCORES["stable"]
    if trend == favorable:
        return _TREND_SCORES["favorable"]
    return _TREND_SCORES["unfavorable"]


def _prophet_uncertainty_score(forecasts: dict) -> float:
    """
    For each Prophet forecast series, compute normalised band width:
        band_width = mean(upper − lower) / |mean(values)|
    certainty = max(0, 1 − band_width)
    Average across all series.  Tighter bands → higher score.
    """
    scores: list[float] = []
    for fc in forecasts.values():
        vals   = [e["value"] for e in fc.get("values", [])            if isinstance(e, dict) and "value" in e]
        upper  = [e["value"] for e in fc.get("uncertainty_upper", []) if isinstance(e, dict) and "value" in e]
        lower  = [e["value"] for e in fc.get("uncertainty_lower", []) if isinstance(e, dict) and "value" in e]

        if not (vals and upper and lower and len(vals) == len(upper) == len(lower)):
            continue
        mean_val  = sum(vals) / len(vals)
        if mean_val == 0:
            continue
        mean_band = sum(u - l for u, l in zip(upper, lower)) / len(vals)
        scores.append(max(0.0, 1.0 - (mean_band / abs(mean_val))))

    return sum(scores) / len(scores) if scores else 0.50


def compute_confidence_score(ms: dict, use_case: str) -> float:
    """
    Weighted formula:
        confidence = 0.40 × volatility_stability
                   + 0.35 × prophet_certainty
                   + 0.25 × sentiment_normalized   (sentiment −1..1 → 0..1)

    Returns a float in [0, 1].
    """
    ei = ms.get("economic_indicators", {})

    # Component 1 — economic volatility (40%)
    key_indicators = ["cpi", "unemployment", "gdp", "sector_consumer_spending", "interest_rate"]
    stab_scores = [
        _trend_stability(ei[k].get("trend", "stable"), k, use_case)
        for k in key_indicators if k in ei
    ]
    volatility_score = sum(stab_scores) / len(stab_scores) if stab_scores else 0.50

    # Component 2 — Prophet forecast certainty (35%)
    uncertainty_score = _prophet_uncertainty_score(ms.get("forecasts", {}))

    # Component 3 — news sentiment (25%)
    raw_sentiment     = ms.get("news_context", {}).get("sentiment_score", 0.0)
    sentiment_norm    = (raw_sentiment + 1.0) / 2.0  # −1..1 → 0..1

    score = 0.40 * volatility_score + 0.35 * uncertainty_score + 0.25 * sentiment_norm
    return round(score, 3)


# ── Projection Builder ────────────────────────────────────────────────────────

def _build_projections(ms: dict, base_revenue: float, base_footfall: float,
                       decision_ratio: float = 1.0, horizon: int = 6) -> dict:
    """
    Use Prophet sector_spending_forecast from MS to project an N-month trajectory.
    The decision_ratio (OP2_revenue / OP1_revenue) scales OP2 projections on top.
    horizon is passed from IP2.forecast_horizon (default 6, clamped 1–24).

    Rule: growth_factor = forecast_value / current_value
          projected = base × growth_factor × decision_ratio
    """
    ei            = ms.get("economic_indicators", {})
    fc            = ms.get("forecasts", {})
    sector_fc     = fc.get("sector_spending_forecast", {}).get("values", [])
    current_spend = ei.get("sector_consumer_spending", {}).get("current", 1.0) or 1.0

    revenue_nm:  list[dict] = []
    footfall_nm: list[dict] = []

    for i, entry in enumerate(sector_fc[:horizon]):
        val    = entry["value"] if isinstance(entry, dict) else current_spend
        growth = val / current_spend
        revenue_nm.append({"month": i + 1, "value": round(base_revenue * growth * decision_ratio, 2)})
        footfall_nm.append({"month": i + 1, "value": round(base_footfall * growth * decision_ratio, 0)})

    # Fallback: if MS has no forecast data, project flat
    if not revenue_nm:
        for i in range(horizon):
            revenue_nm.append({"month": i + 1, "value": round(base_revenue * decision_ratio, 2)})
            footfall_nm.append({"month": i + 1, "value": round(base_footfall * decision_ratio, 0)})

    market_growth = ei.get("sector_growth_rate", {}).get("current", 0.0)
    return {
        "revenue_6m":    revenue_nm,
        "footfall_6m":   footfall_nm,
        "market_growth": round(market_growth, 4),
    }


# ── Use-Case Formula Functions ────────────────────────────────────────────────
#
# Each function receives (ip1, ip2, ms) and returns:
#   (fin_op1, fin_op2, base_footfall_op1, base_footfall_op2)
#
# fin_op* dicts match the OP financials schema.

def _pricing_change(ip1: dict, ip2: dict, ms: dict) -> tuple[dict, dict, float, float]:
    """
    Pricing Change use case.

    Core formula — Price Elasticity of Demand:
        %ΔQ = price_elasticity × %ΔP
        new_footfall = old_footfall × (1 + price_elasticity × price_change_pct)
        new_revenue  = new_footfall × new_avg_ticket

    Sentiment dampener (±3% max):
        revenue_op2 *= 1 + (sentiment_score × 0.03)

    Labor cost adjustment (volume-driven):
        new_cogs = cogs × (1 + labor_elasticity × volume_change × labor_cost_ratio)

    All other modifiers come from MS — no LLM here.
    """
    el          = ms.get("elasticity_modifiers", {})
    price_el    = el.get("price_elasticity", -0.8)    # typically negative
    sentiment   = ms.get("news_context", {}).get("sentiment_score", 0.0)

    rev_op1        = float(ip1["monthly_revenue"])
    fixed_op1      = float(ip1.get("monthly_fixed_costs",  ip1["monthly_costs"] * 0.30))
    variable_op1   = float(ip1.get("monthly_variable_costs", ip1["monthly_costs"] * 0.70))
    cogs_op1       = fixed_op1 + variable_op1          # total operating costs
    footfall_op1   = float(ip1.get("monthly_footfall", 0))
    avg_ticket_op1 = float(ip1.get("avg_price_point",
                                   rev_op1 / max(footfall_op1, 1)))

    delta_p       = float(ip2.get("price_change_pct", 0.0))
    volume_change = price_el * delta_p                 # e.g. −0.8 × 0.10 = −0.08

    new_footfall   = footfall_op1 * (1 + volume_change)
    new_avg_ticket = avg_ticket_op1 * (1 + delta_p)
    rev_op2        = new_footfall * new_avg_ticket * (1 + sentiment * 0.03)

    # Fixed costs stay constant; variable costs (supplies + wages) scale with volume
    new_variable   = variable_op1 * (1 + volume_change)
    cogs_op2       = fixed_op1 + new_variable

    profit_op1 = rev_op1 - cogs_op1
    profit_op2 = rev_op2 - cogs_op2

    fin_op1 = {
        "revenue":    round(rev_op1, 2),
        "profit":     round(profit_op1, 2),
        "margin":     round(profit_op1 / rev_op1, 4) if rev_op1 else 0,
        "break_even": round(cogs_op1, 2),
        "cogs":       round(cogs_op1, 2),
        "avg_ticket": round(avg_ticket_op1, 2),
        "footfall":   round(footfall_op1),
    }
    fin_op2 = {
        "revenue":    round(rev_op2, 2),
        "profit":     round(profit_op2, 2),
        "margin":     round(profit_op2 / rev_op2, 4) if rev_op2 else 0,
        "break_even": round(cogs_op2, 2),
        "cogs":       round(cogs_op2, 2),
        "avg_ticket": round(new_avg_ticket, 2),
        "footfall":   round(new_footfall),
    }
    return fin_op1, fin_op2, footfall_op1, new_footfall


def _target_audience(ip1: dict, ip2: dict, ms: dict) -> tuple[dict, dict, float, float]:
    """
    Target Audience use case.

    Logic:
    - Demographic multiplier: Census income_distribution → higher income target
      → higher avg ticket (rule table, not ML).
    - Reach increase (ip2.expected_reach_increase) drives footfall growth.
    - Sentiment boosts/dampens footfall by ±5%.
    - Marketing spend (ip2.marketing_spend_increase × revenue) added to COGS.
    """
    el           = ms.get("elasticity_modifiers", {})
    sentiment    = ms.get("news_context", {}).get("sentiment_score", 0.0)
    demo_data    = ms.get("demographic_data", {})
    income_dist  = demo_data.get("income_distribution", {})

    rev_op1        = float(ip1["monthly_revenue"])
    fixed_op1      = float(ip1.get("monthly_fixed_costs",  ip1["monthly_costs"] * 0.30))
    variable_op1   = float(ip1.get("monthly_variable_costs", ip1["monthly_costs"] * 0.70))
    cogs_op1       = fixed_op1 + variable_op1
    footfall_op1   = float(ip1.get("monthly_footfall", 0))
    avg_ticket_op1 = float(ip1.get("avg_price_point",
                                   rev_op1 / max(footfall_op1, 1)))

    target_demo          = ip2.get("target_demographic", "18_34")
    reach_increase       = float(ip2.get("expected_reach_increase", 0.15))
    marketing_spend_pct  = float(ip2.get("marketing_spend_increase", 0.10))

    # Rule: demographic ticket multiplier — informed by Census income share
    high_income_share = float(income_dist.get("above_100k", 0.20))
    _BASE_DEMO_MULT = {"18_34": 0.95, "35_54": 1.08, "55_plus": 1.12}
    demo_mult = _BASE_DEMO_MULT.get(target_demo, 1.0) * (1.0 + high_income_share * 0.20)

    new_footfall   = footfall_op1 * (1 + reach_increase) * (1 + sentiment * 0.05)
    new_avg_ticket = avg_ticket_op1 * demo_mult
    rev_op2        = new_footfall * new_avg_ticket

    # Variable costs scale with new footfall volume; fixed costs stay constant
    volume_ratio   = new_footfall / max(footfall_op1, 1)
    new_variable   = variable_op1 * volume_ratio
    marketing_cost = rev_op1 * marketing_spend_pct   # one-time spend, additive
    cogs_op2       = fixed_op1 + new_variable + marketing_cost

    profit_op1 = rev_op1 - cogs_op1
    profit_op2 = rev_op2 - cogs_op2

    fin_op1 = {
        "revenue":    round(rev_op1, 2),
        "profit":     round(profit_op1, 2),
        "margin":     round(profit_op1 / rev_op1, 4) if rev_op1 else 0,
        "break_even": round(cogs_op1, 2),
        "cogs":       round(cogs_op1, 2),
        "avg_ticket": round(avg_ticket_op1, 2),
        "footfall":   round(footfall_op1),
    }
    fin_op2 = {
        "revenue":    round(rev_op2, 2),
        "profit":     round(profit_op2, 2),
        "margin":     round(profit_op2 / rev_op2, 4) if rev_op2 else 0,
        "break_even": round(cogs_op2, 2),
        "cogs":       round(cogs_op2, 2),
        "avg_ticket": round(new_avg_ticket, 2),
        "footfall":   round(new_footfall),
    }
    return fin_op1, fin_op2, footfall_op1, new_footfall


def _franchising(ip1: dict, ip2: dict, ms: dict) -> tuple[dict, dict, float, float]:
    """
    Franchising use case.

    Logic:
    - New revenue per location discounted by market saturation index (0–1 scale from Census).
      Rule: effective_revenue = expected_revenue × (1 − saturation × 0.30)
    - Investment amortized over 24 months (standard SMB payback window).
    - New location COGS = 75% of original COGS (economies of scale, but less efficient initially).
    - Footfall: new locations don't perfectly add up due to shared trade zone demand.
      Rule: new_total_footfall = original × (1 + n_locations × 0.70)
    - Break-even returned in months, not dollars.
    """
    sentiment     = ms.get("news_context", {}).get("sentiment_score", 0.0)
    market_data   = ms.get("market_data", {})

    rev_op1        = float(ip1["monthly_revenue"])
    fixed_op1      = float(ip1.get("monthly_fixed_costs",  ip1["monthly_costs"] * 0.30))
    variable_op1   = float(ip1.get("monthly_variable_costs", ip1["monthly_costs"] * 0.70))
    cogs_op1       = fixed_op1 + variable_op1
    footfall_op1   = float(ip1.get("monthly_footfall", 0))
    avg_ticket     = float(ip1.get("avg_price_point", 0))
    profit_op1     = rev_op1 - cogs_op1

    n_loc           = int(ip2.get("new_locations", 1))
    invest_per_loc  = float(ip2.get("investment_per_location", 50_000))
    rev_per_loc     = float(ip2.get("expected_revenue_per_location", rev_op1 * 0.80))
    royalty_pct     = float(ip2.get("royalty_pct", 0.0))   # fraction, e.g. 0.06 = 6%

    saturation          = float(market_data.get("market_saturation_index", 0.30))
    saturation_discount = saturation * 0.30

    new_revenue_raw  = n_loc * rev_per_loc * (1 - saturation_discount)
    new_revenue_adj  = new_revenue_raw * (1 + sentiment * 0.05)
    # Royalty income: ongoing % of each new location's revenue paid to the franchisor
    royalty_income   = new_revenue_adj * royalty_pct
    rev_op2          = rev_op1 + new_revenue_adj + royalty_income

    # New location costs: fixed (rent, utilities for new location) estimated at 60% of
    # original fixed costs, variable at 80% of original variable costs (less efficient initially).
    # Plus amortized investment over 36 months (more realistic than 24).
    total_invest      = n_loc * invest_per_loc
    amort_monthly     = total_invest / 36
    new_loc_fixed     = fixed_op1 * n_loc * 0.60
    new_loc_variable  = variable_op1 * n_loc * 0.80
    cogs_op2          = cogs_op1 + new_loc_fixed + new_loc_variable + amort_monthly

    profit_op2        = rev_op2 - cogs_op2
    margin_op2        = profit_op2 / rev_op2 if rev_op2 else 0
    incremental_profit = profit_op2 - profit_op1
    # Break-even in months; cap at 120 (10 years) if unprofitable
    if incremental_profit > 0:
        break_even_months = min(total_invest / incremental_profit, 120.0)
    else:
        break_even_months = 120.0

    new_footfall     = footfall_op1 * (1 + n_loc * 0.70)

    fin_op1 = {
        "revenue":    round(rev_op1, 2),
        "profit":     round(profit_op1, 2),
        "margin":     round(profit_op1 / rev_op1, 4) if rev_op1 else 0,
        "break_even": round(cogs_op1, 2),
        "cogs":       round(cogs_op1, 2),
        "avg_ticket": round(avg_ticket, 2),
        "footfall":   round(footfall_op1),
    }
    fin_op2 = {
        "revenue":             round(rev_op2, 2),
        "profit":              round(profit_op2, 2),
        "margin":              round(margin_op2, 4),
        "break_even":          round(cogs_op2, 2),
        "break_even_months":   round(break_even_months, 1),
        "cogs":                round(cogs_op2, 2),
        "avg_ticket":          round(avg_ticket, 2),
        "footfall":            round(new_footfall),
    }
    return fin_op1, fin_op2, footfall_op1, new_footfall


# ── Dispatch Table ────────────────────────────────────────────────────────────

_FORMULA: dict[str, Any] = {
    "pricing":         _pricing_change,
    "target_audience": _target_audience,
    "franchising":     _franchising,
}


# ── Main Entry Point ──────────────────────────────────────────────────────────

def run_simulation(ms: dict, ip1: dict, ip2: dict) -> dict:
    """
    Run the simulation and return {"op1": ..., "op2": ...}.

    Steps:
    1. Identify use case from IP2.
    2. Run use-case formula → OP1 financials (control) + OP2 financials (experiment).
    3. Build 6-month projections from MS Prophet forecasts.
    4. Compute confidence score from MS.
    5. Compute delta (OP2 − OP1).
    6. Assemble and return OP1 + OP2 in the output schema.
    """
    use_case = ip2.get("use_case", "pricing")
    if use_case not in _FORMULA:
        raise ValueError(
            f"Unknown use_case '{use_case}'. Valid options: {list(_FORMULA.keys())}"
        )

    formula_fn                               = _FORMULA[use_case]
    fin_op1, fin_op2, foot_op1, foot_op2    = formula_fn(ip1, ip2, ms)

    confidence   = compute_confidence_score(ms, use_case)
    sentiment    = ms.get("news_context", {}).get("sentiment_score", 0.0)
    flags        = ms.get("news_context", {}).get("flags", [])

    # Projection ratio: how much bigger/smaller OP2 revenue trajectory is vs OP1
    decision_ratio   = fin_op2["revenue"] / fin_op1["revenue"] if fin_op1["revenue"] else 1.0
    forecast_horizon = int(ip2.get("forecast_horizon", 6))
    forecast_horizon = min(24, max(1, forecast_horizon))

    proj_op1 = _build_projections(ms, fin_op1["revenue"], foot_op1, decision_ratio=1.0,          horizon=forecast_horizon)
    proj_op2 = _build_projections(ms, fin_op2["revenue"], foot_op2, decision_ratio=decision_ratio, horizon=forecast_horizon)

    delta = {
        "revenue_delta": round(fin_op2["revenue"] - fin_op1["revenue"], 2),
        "profit_delta":  round(fin_op2["profit"]  - fin_op1["profit"],  2),
        "margin_delta":  round(fin_op2["margin"]  - fin_op1["margin"],  4),
    }

    risk_block = {
        "confidence_score": confidence,
        "sentiment_score":  sentiment,
        "flags":            flags,
    }

    return {
        "op1": {
            "financials":  fin_op1,
            "projections": proj_op1,
            "risk":        risk_block,
            "delta":       {},
        },
        "op2": {
            "financials":  fin_op2,
            "projections": proj_op2,
            "risk":        risk_block,
            "delta":       delta,
        },
    }


def write_op(op: dict, use_case: str, business_id: str) -> str:
    """
    Write OP file to backend/data/op/.

    Naming convention:
        op_<use_case>_<business_id>_<date>.json

    Args:
        op:          result dict from run_simulation() — {"op1": ..., "op2": ...}
        use_case:    "pricing" | "franchising" | "target_audience"
        business_id: business ID from enrollment record

    Returns:
        Path to written OP file
    """
    today = date.today().isoformat()
    os.makedirs(OP_DIR, exist_ok=True)
    path = os.path.join(OP_DIR, f"op_{use_case}_{business_id}_{today}.json")
    with open(path, "w") as f:
        json.dump(op, f, indent=2)
    print(f"[sim_layer] OP file written to: {path}")
    return path
