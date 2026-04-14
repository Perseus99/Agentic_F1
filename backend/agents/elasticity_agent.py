"""
Elasticity Agent — reasons about market elasticity parameters from economic context.

Replaces the fixed-formula approach in elasticity.py with LLM reasoning that:
1. Calls compute_formula_baseline tool to get formula-derived starting values
2. Considers business type, industry, and local market context
3. Adjusts values where business reasoning suggests the formula misses nuance
4. Returns calibrated values with a brief rationale

Falls back to formula values silently if the agent fails or produces invalid output.
"""
import json
import sys
import os

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ML_DIR  = os.path.join(_BACKEND, "ml")
for _p in [_BACKEND, _ML_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from agents.base import run_agent

# Valid ranges for each elasticity value — enforced as hard clamps on agent output
_RANGES = {
    "price_elasticity":  (-2.0, -0.5),   # negative: higher magnitude = more price-sensitive
    "labor_elasticity":  (0.5,  2.0),    # higher = labor is expensive / scarce
    "demand_elasticity": (-1.0, 1.0),    # positive = growing demand, negative = contracting
    "market_elasticity": (0.0,  1.0),    # higher = more market saturation
}

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "compute_formula_baseline",
            "description": (
                "Computes elasticity values using deterministic formulas based on "
                "CPI, unemployment, GDP, and sector spending data. "
                "Returns formula-derived baseline values. You may adjust these "
                "based on the business type and market context."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
]

_SYSTEM = """You are an economic analyst calibrating market elasticity parameters for a small business financial simulation.

The simulation engine uses four parameters:
- price_elasticity     (range -2.0 to -0.5): how sensitive customers are to price changes
  * -2.0 = very price-sensitive (luxury, competitive market)
  * -0.5 = price-insensitive (essential service, monopoly)
- labor_elasticity     (range 0.5 to 2.0): cost/availability pressure for hiring
  * 2.0 = expensive and scarce labor
  * 0.5 = cheap and abundant labor
- demand_elasticity    (range -1.0 to 1.0): whether sector demand is growing or contracting
  * 1.0 = strong demand growth
  * -1.0 = contracting demand
- market_elasticity    (range 0.0 to 1.0): local market saturation
  * 1.0 = highly saturated (many competitors)
  * 0.0 = underserved market

Your job:
1. Call compute_formula_baseline to see the formula-derived starting values
2. Consider the business type and context — adjust where business logic warrants it
   (e.g. a bakery is less price-elastic than a luxury goods store; food service has tight labor)
3. Return calibrated JSON only — no markdown, no explanation outside the rationale field

Output format (valid JSON only, no code fences):
{
  "price_elasticity": <float between -2.0 and -0.5>,
  "labor_elasticity": <float between 0.5 and 2.0>,
  "demand_elasticity": <float between -1.0 and 1.0>,
  "market_elasticity": <float between 0.0 and 1.0>,
  "rationale": "<1-2 sentences on the key adjustments made and why>"
}"""


def _make_baseline_fn(raw_data: dict):
    """Returns a closure that computes formula baseline from captured raw_data."""
    def _compute():
        from elasticity import compute_elasticity
        baseline = compute_elasticity(raw_data)
        return {
            "formula_values": baseline,
            "note": "These are formula-derived baselines. Adjust if business context warrants it.",
        }
    return _compute


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _extract_json(text: str) -> dict | None:
    """
    Extract the first JSON object from text, handling:
    - Bare JSON
    - ```json ... ``` code fence anywhere in the response
    - Prose text before/after the JSON block
    """
    import re

    text = text.strip()

    # 1. Try bare parse first (clean output)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Look for ```json ... ``` block anywhere in the response
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Find outermost { ... } block (last resort)
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


def _parse_and_validate(text: str) -> dict | None:
    """
    Parse agent JSON output and validate ranges.
    Returns validated dict or None if parsing/validation fails.
    """
    parsed = _extract_json(text or "")
    if parsed is None:
        return None

    validated = {}
    for key, (lo, hi) in _RANGES.items():
        if key not in parsed:
            return None  # Missing required field
        try:
            validated[key] = round(_clamp(float(parsed[key]), lo, hi), 3)
        except (TypeError, ValueError):
            return None

    validated["rationale"] = str(parsed.get("rationale", ""))
    return validated


def calibrate_elasticity(raw_data: dict, context: dict) -> dict:
    """
    Elasticity Agent entry point.

    Args:
        raw_data: fetcher output (fred, bls, bea, census keys)
        context:  business context dict (business_type, naics_code, city, state, ...)

    Returns:
        {price_elasticity, labor_elasticity, demand_elasticity, market_elasticity}
        Same shape as compute_elasticity() — rationale is logged, not returned.
    """
    from elasticity import compute_elasticity
    from utils import get_latest, get_trend

    # Always compute formula baseline — used as fallback if agent fails
    formula = compute_elasticity(raw_data)

    fred = raw_data.get("fred", {})
    bls  = raw_data.get("bls", {})

    cpi_current   = get_latest(fred.get("cpi", []))
    cpi_trend     = get_trend(fred.get("cpi", []))
    gdp_trend     = get_trend(fred.get("gdp", []))
    unemp_current = get_latest(bls.get("unemployment", []))
    unemp_trend   = get_trend(bls.get("unemployment", []))

    user_message = (
        f"Business type: {context.get('business_type', 'retail')}\n"
        f"NAICS code:    {context.get('naics_code', 'unknown')}\n"
        f"Location:      {context.get('city', '')}, {context.get('state', '')}\n\n"
        "Current economic indicators:\n"
        f"  CPI:          {cpi_current:.1f} (trend: {cpi_trend})\n"
        f"  Unemployment: {unemp_current:.1f}% (trend: {unemp_trend})\n"
        f"  GDP trend:    {gdp_trend}\n\n"
        "Call compute_formula_baseline first, then return your calibrated JSON."
    )

    print("[elasticity_agent] Reasoning about elasticity parameters...")

    try:
        raw_response = run_agent(
            system_prompt=_SYSTEM,
            user_message=user_message,
            tools=_TOOLS,
            tool_functions={"compute_formula_baseline": _make_baseline_fn(raw_data)},
            max_iterations=4,
        )

        validated = _parse_and_validate(raw_response or "")

        if validated is None:
            print("[elasticity_agent] Could not parse agent output — using formula fallback")
            return formula

        rationale = validated.pop("rationale", "")
        if rationale:
            print(f"[elasticity_agent] Rationale: {rationale}")

        # Log comparison so differences are visible in server logs
        for key in _RANGES:
            formula_val = formula.get(key)
            agent_val   = validated.get(key)
            if formula_val != agent_val:
                print(f"[elasticity_agent]   {key}: formula={formula_val} → agent={agent_val}")
            else:
                print(f"[elasticity_agent]   {key}: {agent_val} (unchanged from formula)")

        return validated

    except Exception as e:
        print(f"[elasticity_agent] Agent failed ({e}) — using formula fallback")
        return formula
