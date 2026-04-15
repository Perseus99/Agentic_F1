"""
TwinTrack — Simulation Layer
================================
Input:  MS  (market snapshot: economic indicators + ARIMA forecasts + sentiment)
        IP1 (business financials: current state)
        IP2 (decision being simulated: use case + parameters)

Output: OP1 (base case — control, no change applied)
        OP2 (experiment — decision applied, modifiers layered on top)

Decision approach
-----------------
- ALL calculations are rules-based / formula-driven.  No LLM calls here.
- ARIMA forecast values are READ from MS.forecasts (computed in ML layer).
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


def _prophet_uncertainty_score(forecasts: dict) -> float:
    """
    For each ARIMA forecast series, compute normalised band width:
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

    # No real forecast data → penalise to 0.35 (absent data is a weakness,
    # not a neutral state — the old default of 0.50 was misleading)
    return sum(scores) / len(scores) if scores else 0.35


def _input_plausibility_score(ip1: dict, ip2: dict, use_case: str) -> float:
    """
    Score 0–1: are the inputs internally consistent and within the model's
    calibrated operating range?

    Catches garbage-in / extrapolation-territory before they inflate confidence.
    """
    revenue = float(ip1.get("monthly_revenue", 0))
    costs   = float(ip1.get("monthly_costs",   0))

    if revenue <= 0:
        return 0.10   # no revenue data → cannot trust any output

    margin = (revenue - costs) / revenue
    score  = 1.0

    if not (0.0 <= margin <= 0.90):
        score -= 0.30   # implausible margin (negative or suspiciously high)

    if use_case == "pricing":
        pct = abs(float(ip2.get("price_change_pct", 0)))
        if pct > 20:
            score -= 0.20   # extrapolation territory — model wasn't calibrated here
        if pct > 35:
            score -= 0.20   # severe extrapolation — double-penalise

    elif use_case == "franchising":
        if margin < 0.15:
            score -= 0.30   # margin too thin to support replicable franchise unit economics

    return round(max(0.10, min(1.0, score)), 3)


def _assumption_alignment_score(ms: dict, ip1: dict, ip2: dict, use_case: str) -> float:
    """
    Score 0–1: do the model's core assumptions hold given current market signals?

    This replaces the old 'volatility_stability' component.  The key difference:
    instead of scoring whether the macro environment is *good*, we score whether
    the simulation's specific causal assumptions are *valid*.

    Examples:
      pricing   — core assumption: customers absorb the price change.
                  Strained by high price elasticity + rising CPI.
      audience  — core assumption: the target demographic exists locally and
                  can be reached with the stated budget.
      franchise — core assumption: capital is accessible and unit economics replicate.
                  Strained by rising interest rates or thin margins.
    """
    econ  = ms.get("economic_indicators", {})
    elast = ms.get("elasticity_modifiers", {})
    demo  = ms.get("demographic_data", {})

    score = 0.80   # start moderately confident; deductions are evidence-based

    if use_case == "pricing":
        change_pct   = float(ip2.get("price_change_pct", 0))
        price_elast  = float(elast.get("price_elasticity", -1.0))
        cpi_trend    = econ.get("cpi", {}).get("trend", "stable")
        sector_trend = econ.get("sector_consumer_spending", {}).get("trend", "stable")

        # Assumption: customers absorb the hike.
        # Very negative elasticity = demand is highly price-sensitive.
        if change_pct > 0 and price_elast < -1.5:
            score -= 0.20
        # Double squeeze: asking customers to pay more while CPI already erodes purchasing power.
        if change_pct > 0 and cpi_trend == "rising":
            score -= 0.15
        # Sector shrinking: a price hike into falling demand compounds risk.
        if change_pct > 0 and sector_trend == "falling":
            score -= 0.15

    elif use_case == "target_audience":
        target_demo = ip2.get("audience_shift", ip2.get("target_demographic", "35_54"))
        income_dist = demo.get("income_distribution", {})
        mkt_budget  = float(ip2.get("marketing_spend_pct", ip2.get("marketing_budget_pct", 0.08)))
        if mkt_budget > 1:
            mkt_budget /= 100   # normalise pct-as-integer (e.g. 8 → 0.08)

        # Assumption: the target demographic exists in meaningful numbers locally.
        segment_share = {
            "18_34":   income_dist.get("below_50k",   0.45),
            "35_54":   income_dist.get("50k_100k",    0.35),
            "55_plus": income_dist.get("above_100k",  0.20),
        }.get(target_demo, 0.30)

        if segment_share < 0.15:
            score -= 0.20   # target segment too small locally to drive material lift
        if mkt_budget < 0.05:
            score -= 0.15   # underfunded — can't meaningfully reach the segment

    elif use_case == "franchising":
        interest_trend = econ.get("interest_rate", {}).get("trend", "stable")
        revenue        = float(ip1.get("monthly_revenue", 0))
        costs          = float(ip1.get("monthly_costs",   0))
        margin         = (revenue - costs) / revenue if revenue > 0 else 0.0

        # Assumption: capital is accessible and unit economics replicate.
        if interest_trend == "rising":
            score -= 0.20   # higher borrowing cost threatens franchisee ROI
        if margin < 0.20:
            score -= 0.20   # thin margins → hard for new locations to be profitable

    return round(max(0.10, min(1.0, score)), 3)


def compute_confidence_score(ms: dict, use_case: str,
                             ip1: dict | None = None,
                             ip2: dict | None = None) -> float:
    """
    Weighted formula:
        confidence = 0.30 × input_plausibility
                   + 0.40 × assumption_alignment
                   + 0.30 × forecast_data_quality

    All three components measure model trustworthiness, not environment
    favourability (the old formula conflated the two):

    input_plausibility    — are inputs consistent and within calibrated range?
    assumption_alignment  — do the model's causal assumptions hold given market signals?
    forecast_data_quality — are projections grounded in real forecast data?

    The Critique Agent applies further deductions post-simulation for specific
    contradictions it identifies through reasoning.

    Returns a float in [0, 1].
    """
    ip1 = ip1 or {}
    ip2 = ip2 or {}

    plausibility  = _input_plausibility_score(ip1, ip2, use_case)
    alignment     = _assumption_alignment_score(ms, ip1, ip2, use_case)
    forecast_qual = _prophet_uncertainty_score(ms.get("forecasts", {}))

    score = 0.30 * plausibility + 0.40 * alignment + 0.30 * forecast_qual
    return round(min(1.0, max(0.0, score)), 3)


# ── Projection Builder ────────────────────────────────────────────────────────

_PROJECTION_DECAY = 0.92   # per-month decay of the OP1→OP2 gap
# A price hike or audience shift has its strongest effect in month 1 (customers
# react immediately) then the market absorbs it — competitors adjust, customers
# habituate, word-of-mouth settles. By month 6: effect is at ~0.92^5 ≈ 66%.
# OP1 is unaffected (decision_ratio = 1.0 → decay term is 0).


def _build_projections(ms: dict, base_revenue: float, base_footfall: float,
                       decision_ratio: float = 1.0, horizon: int = 6) -> dict:
    """
    Build an N-month revenue/footfall projection using a composite economic
    growth factor derived from three forecast signals:

        spending_growth  — sector consumer spending trajectory (primary, 50%)
        gdp_modifier     — GDP forecast partial pass-through (30%)
        cpi_modifier     — CPI dampening on real purchasing power (20%)

    All three forecast series are monthly-upsampled in the ML layer so there
    is always one data point per month; no more fallback after month 2.

    The decision_ratio (OP2_revenue / OP1_revenue) is applied on top with
    exponential decay so the OP1/OP2 gap converges over time.

    Formula per month i:
        growth       = spending_growth × gdp_modifier × cpi_modifier
        decayed      = 1 + (decision_ratio − 1) × DECAY^i
        projected    = base × growth × decayed
    """
    ei = ms.get("economic_indicators", {})
    fc = ms.get("forecasts", {})

    sector_fc = fc.get("sector_spending_forecast", {}).get("values", [])
    gdp_fc    = fc.get("gdp_forecast",             {}).get("values", [])
    cpi_fc    = fc.get("cpi_forecast",             {}).get("values", [])

    current_spend = ei.get("sector_consumer_spending", {}).get("current", 1.0) or 1.0
    current_gdp   = ei.get("gdp",   {}).get("current", 1.0) or 1.0
    current_cpi   = ei.get("cpi",   {}).get("current", 1.0) or 1.0

    revenue_nm:  list[dict] = []
    footfall_nm: list[dict] = []

    for i in range(horizon):
        # ── Sector spending growth (50% weight — primary demand signal) ──────
        if i < len(sector_fc):
            spend_val       = sector_fc[i]["value"] if isinstance(sector_fc[i], dict) else current_spend
            spending_growth = spend_val / current_spend
        else:
            spending_growth = 1.0

        # ── GDP modifier (30% weight — partial macro pass-through) ───────────
        # Rising GDP lifts consumer activity; only 30% passes through to a
        # single sector (the rest goes to savings, other sectors, etc.)
        if i < len(gdp_fc):
            gdp_val      = gdp_fc[i]["value"] if isinstance(gdp_fc[i], dict) else current_gdp
            gdp_modifier = 1.0 + (gdp_val / current_gdp - 1.0) * 0.3
        else:
            gdp_modifier = 1.0

        # ── CPI dampening (20% weight — inflation erodes real purchasing power)
        # Rising prices reduce real discretionary spend at 20% pass-through.
        if i < len(cpi_fc):
            cpi_val      = cpi_fc[i]["value"] if isinstance(cpi_fc[i], dict) else current_cpi
            cpi_modifier = 1.0 - (cpi_val / current_cpi - 1.0) * 0.2
        else:
            cpi_modifier = 1.0

        growth  = spending_growth * gdp_modifier * cpi_modifier
        decayed = 1.0 + (decision_ratio - 1.0) * (_PROJECTION_DECAY ** i)

        revenue_nm.append( {"month": i + 1, "value": round(base_revenue  * growth * decayed, 2)})
        footfall_nm.append({"month": i + 1, "value": round(base_footfall * growth * decayed, 0)})

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

    # Demographic ticket multiplier scaled by the income tier that corresponds to
    # the target segment — each group's spending power comes from its own income tier,
    # not the city-wide above_100k share (the old code applied the high-income share
    # as a booster even for 18-34 targets, which skewed results in wealthy metros).
    _BASE_DEMO_MULT = {"18_34": 0.95, "35_54": 1.08, "55_plus": 1.12}
    _DEMO_INCOME_KEY = {
        "18_34":   "below_50k",   # young adults concentrated in lower income brackets
        "35_54":   "50k_100k",    # peak earning years → middle income tier
        "55_plus": "above_100k",  # established wealth / retirement savings
    }
    income_key        = _DEMO_INCOME_KEY.get(target_demo, "50k_100k")
    segment_income    = float(income_dist.get(income_key, 0.33))
    demo_mult = _BASE_DEMO_MULT.get(target_demo, 1.0) * (1.0 + segment_income * 0.20)

    new_footfall   = footfall_op1 * (1 + reach_increase) * (1 + sentiment * 0.05)
    new_avg_ticket = avg_ticket_op1 * demo_mult
    rev_op2        = new_footfall * new_avg_ticket

    # Variable costs scale with new footfall volume; fixed costs stay constant
    volume_ratio   = new_footfall / max(footfall_op1, 1)
    new_variable   = variable_op1 * volume_ratio
    marketing_cost = rev_op2 * marketing_spend_pct   # scales with new revenue, not baseline
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

    # Revenue model depends on ownership structure:
    #   royalty_pct > 0  → franchisee-operated: owner collects royalty % only
    #                       (franchisee keeps the rest — adding full revenue AND
    #                        royalty would double-count the same cash flow)
    #   royalty_pct == 0 → company-owned expansion: owner captures full revenue
    if royalty_pct > 0:
        rev_from_new = new_revenue_adj * royalty_pct
    else:
        rev_from_new = new_revenue_adj
    rev_op2 = rev_op1 + rev_from_new

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
    3. Build 6-month projections from MS ARIMA forecasts.
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

    confidence   = compute_confidence_score(ms, use_case, ip1=ip1, ip2=ip2)
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
