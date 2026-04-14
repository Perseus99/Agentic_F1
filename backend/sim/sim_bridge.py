"""
Map TwinTrack UI / twin-layer JSON → IP1 + IP2 for sim_layer.run_simulation.
"""

from __future__ import annotations
from typing import Any
import os
import sys

# Make backend/ importable so agents package is accessible from sim/
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from agents.simulation_agent import resolve_demographic as _agent_resolve_demographic

_VALID_DEMOS = {"18_34", "35_54", "55_plus"}


def _resolve_demographic(text: str) -> str:
    """
    Use the Simulation Agent (Ollama) to map any freetext audience description
    to one of the three demographic keys: 18_34, 35_54, 55_plus.
    Falls back to 35_54 on any error.
    """
    return _agent_resolve_demographic(text)


def twin_layer_to_ip1(twin: dict[str, Any]) -> dict[str, Any]:
    """Derive sim_layer IP1 from the canonical Register-business JSON."""

    # ── Revenue ──────────────────────────────────────────────────────────────
    r = twin.get("revenue") or {}
    total_annual   = float(r.get("total_annual") or 0)
    monthly_revenue = total_annual / 12.0 if total_annual else 0.0

    # ── Costs ────────────────────────────────────────────────────────────────
    c    = twin.get("costs") or {}
    loan = c.get("loan") or {}
    staff = twin.get("staffing") or {}

    employees = int(staff.get("total_employees") or 0)

    # ── Cost Sanity Checks ───────────────────────────────────────────────────
    # 1. Clamp negatives — any cost entered as negative is a data entry error.
    rent       = max(0.0, float(c.get("monthly_rent")       or 0))
    utilities  = max(0.0, float(c.get("monthly_utilities")  or 0))
    supplies   = max(0.0, float(c.get("monthly_supplies")   or 0))
    wage_bill  = max(0.0, float(staff.get("monthly_wage_bill") or 0))

    # 2. Loan repayment cap — if it exceeds monthly revenue it's almost
    #    certainly a data entry error (e.g. annual figure in a monthly field).
    #    Cap at 20% of monthly revenue as a reasonable upper bound.
    raw_loan_repayment = max(0.0, float(loan.get("monthly_repayment") or 0))
    if monthly_revenue > 0 and raw_loan_repayment > monthly_revenue:
        print(f"[sim_bridge] WARNING: loan repayment ${raw_loan_repayment:.0f} > monthly revenue "
              f"${monthly_revenue:.0f} — capping at 20% of revenue.")
        raw_loan_repayment = monthly_revenue * 0.20

    # 3. Wage floor — if employees are on payroll but wage bill is 0, it almost
    #    certainly means the field was skipped. Estimate using federal min wage
    #    ($7.25/hr × 160 hrs/month) so costs aren't artificially deflated.
    if employees > 0 and wage_bill == 0:
        estimated_wages = employees * 7.25 * 160
        print(f"[sim_bridge] WARNING: {employees} employees but monthly_wage_bill=0 — "
              f"estimating ${estimated_wages:.0f}/mo at federal min wage.")
        wage_bill = estimated_wages

    # 4. Flag any single line item that looks implausibly large (> 50% of revenue).
    #    We don't cap these — they may be real — but log them for visibility.
    if monthly_revenue > 0:
        for label, val in [("rent", rent), ("utilities", utilities), ("supplies", supplies)]:
            if val > monthly_revenue * 0.50:
                print(f"[sim_bridge] WARNING: {label} ${val:.0f} is >{50}% of monthly revenue "
                      f"${monthly_revenue:.0f} — check for misplaced field value.")

    # Fixed costs: don't vary with sales volume
    fixed_costs   = rent + utilities + raw_loan_repayment
    # Variable costs: scale with sales volume
    variable_costs = supplies + wage_bill
    monthly_costs  = fixed_costs + variable_costs

    # 5. Overall cost-to-revenue warning — don't correct, just surface it.
    if monthly_revenue > 0 and monthly_costs > monthly_revenue * 2:
        print(f"[sim_bridge] WARNING: total costs ${monthly_costs:.0f} exceed 2× revenue "
              f"${monthly_revenue:.0f} — simulation will show deep losses.")

    # ── Avg Ticket — weighted lower-quartile across all products ─────────────
    # Uses the 25th percentile of each product's price range rather than the
    # midpoint, because retail transaction volume concentrates at lower price
    # points (e.g. a bakery sells 50× more $4 pastries than $80 custom cakes).
    # Also handles swapped min/max and applies an employee-based sanity cap.
    products = twin.get("products") or []
    channels = r.get("channels") or []

    if products and channels:
        weighted_sum = 0.0
        weight_total = 0.0
        for i, product in enumerate(products):
            pr    = product.get("price_range") or {}
            raw_a = float(pr.get("min") or 0)
            raw_b = float(pr.get("max") or 0)
            # Normalise — swap if entered in reverse
            lo, hi = (min(raw_a, raw_b), max(raw_a, raw_b)) if (raw_a > 0 and raw_b > 0) else (0.0, 0.0)
            # 25th-percentile of range: weights toward the more common lower-priced transactions
            p25 = lo + (hi - lo) * 0.25 if lo > 0 else 0.0

            if i < len(channels):
                weight = float(channels[i].get("percentage") or 0) / 100.0
            else:
                weight = 1.0 / len(products)

            weighted_sum  += p25 * weight
            weight_total  += weight

        avg_price = weighted_sum / weight_total if weight_total > 0 else monthly_revenue / 100.0
    else:
        avg_price = monthly_revenue / 100.0

    # Employee-based sanity cap:
    # A retail employee handles ~5 transactions/hour × 8hrs × 22 days = 880 tx/month max.
    # If the product-derived avg ticket implies fewer transactions than that floor,
    # it's too high — clamp it to the employee-implied value.
    if employees > 0 and monthly_revenue > 0:
        max_monthly_transactions = employees * 880          # upper bound
        employee_implied_ticket  = monthly_revenue / max_monthly_transactions
        # Only apply cap when product-derived price is significantly higher
        if avg_price > employee_implied_ticket * 2:
            avg_price = employee_implied_ticket

    avg_price = round(max(avg_price, 1.0), 2)

    # ── Footfall — derive from revenue and avg ticket ─────────────────────────
    foot = round(monthly_revenue / avg_price, 0)
    foot = max(50.0, foot)

    # ── Meta ─────────────────────────────────────────────────────────────────
    meta = twin.get("meta") or {}
    bp   = twin.get("business_profile") or {}
    loc  = bp.get("location") or {}

    # Derive cogs_pct from computed block if available, else estimate from variable costs
    comp = twin.get("computed") or {}
    cogs_pct_provided = float(comp.get("cogs_percentage") or 0)
    if cogs_pct_provided > 0 and monthly_revenue > 0:
        cogs_monthly = monthly_revenue * cogs_pct_provided
    else:
        cogs_monthly = variable_costs  # best estimate: variable costs ≈ COGS

    return {
        "business_name":        str(meta.get("business_name") or "Business"),
        "monthly_revenue":      round(monthly_revenue, 2),
        "monthly_costs":        round(monthly_costs, 2),
        "monthly_fixed_costs":  round(fixed_costs, 2),
        "monthly_variable_costs": round(variable_costs, 2),
        "monthly_cogs":         round(cogs_monthly, 2),
        "monthly_footfall":     foot,
        "avg_price_point":      avg_price,
        "employee_count":       employees,
        "naics_code":      "",
        "msa_code":        loc.get("city", "").lower() and "19100" or "19100",
    }


def ui_sim_to_ip2(sim: dict[str, Any], monthly_revenue: float) -> dict[str, Any]:
    """Map React `sim` state to IP2."""
    uc = sim.get("useCase") or sim.get("use_case") or "pricing"

    # Shared: forecast horizon (clamp 1–24 months, default 6)
    _tl  = sim.get("timelineMonths")
    _h   = int(float(_tl) if _tl not in (None, "") else 6)
    _h   = min(24, max(1, _h))

    if uc == "pricing":
        raw = sim.get("priceChangePct")
        pct = float(raw) / 100.0 if raw not in (None, "") else 0.0
        return {"use_case": "pricing", "price_change_pct": pct, "forecast_horizon": _h}

    if uc == "audience":
        mb  = sim.get("marketingBudgetPct")
        msp = float(mb) / 100.0 if mb not in (None, "") else 0.08
        msp = min(0.5, max(0.0, msp))
        # Resolve audienceShift — freetext or structured — to sim_layer key
        raw_demo = str(sim.get("audienceShift") or "").strip()
        target_demo = _resolve_demographic(raw_demo)
        return {
            "use_case":                "target_audience",
            "target_demographic":      target_demo,
            "expected_reach_increase":  0.15,
            "marketing_spend_increase": msp,
            "forecast_horizon":         _h,
        }

    nloc       = int(float(sim.get("newLocations") or 1))
    invest     = float(sim.get("franchiseFee") or 45000)
    rev_pl     = max(1000.0, monthly_revenue * 0.75)
    royalty    = sim.get("royaltyPct")
    royalty_pct = float(royalty) / 100.0 if royalty not in (None, "") else 0.0
    royalty_pct = min(0.5, max(0.0, royalty_pct))  # clamp 0–50%
    horizon    = int(float(sim.get("timelineMonths") or 6))
    horizon    = min(24, max(1, horizon))           # clamp 1–24 months
    return {
        "use_case":                      "franchising",
        "new_locations":                  max(1, nloc),
        "investment_per_location":        invest,
        "expected_revenue_per_location":  rev_pl,
        "royalty_pct":                    royalty_pct,
        "forecast_horizon":               horizon,
    }
