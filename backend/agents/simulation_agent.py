"""
Simulation Agent — resolves target demographics and generates business recommendations.

Tools available to this agent:
  - get_demographic_options: returns the valid demographic bucket keys + descriptions

The agent uses these to map free-text audience descriptions to a structured key,
and also writes plain-English recommendations grounded in simulation numbers.
"""
import json
import sys
import os

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from agents.base import run_agent

_VALID_DEMOS = {"18_34", "35_54", "55_plus"}

# ---------------------------------------------------------------------------
# Demographic resolution
# ---------------------------------------------------------------------------
_DEMO_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_demographic_options",
            "description": "Returns the valid demographic segment keys and their age-group descriptions.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
]


def _get_demographic_options() -> dict:
    return {
        "options": {
            "18_34": "Young adults aged 18–34 (Gen Z / younger Millennials)",
            "35_54": "Middle-aged adults aged 35–54 (older Millennials / Gen X)",
            "55_plus": "Older adults aged 55 and above (Baby Boomers / Silent Gen)",
        }
    }


_DEMO_TOOL_FUNCTIONS = {"get_demographic_options": _get_demographic_options}

_DEMO_SYSTEM = """You are a market demographics specialist.
Your job: map an audience description to exactly one of three demographic segments.
Call the get_demographic_options tool to see the valid options, then reply with
ONLY the segment key — nothing else. Valid keys: 18_34, 35_54, 55_plus."""


def resolve_demographic(description: str) -> str:
    """
    Simulation Agent entry point for demographic resolution.
    Maps free-text audience description → one of {18_34, 35_54, 55_plus}.
    """
    if not description or not description.strip():
        return "35_54"

    cleaned = description.strip().lower()
    if cleaned in _VALID_DEMOS:
        return cleaned

    print(f"[simulation_agent] Resolving demographic: '{description}'...")

    result = run_agent(
        system_prompt=_DEMO_SYSTEM,
        user_message=(
            f'Audience description: "{description}"\n\n'
            "Call get_demographic_options, then reply with ONLY the matching key."
        ),
        tools=_DEMO_TOOLS,
        tool_functions=_DEMO_TOOL_FUNCTIONS,
    )

    result = (result or "35_54").strip().lower().replace(" ", "_")
    if result in _VALID_DEMOS:
        return result
    for key in _VALID_DEMOS:
        if key in result:
            return key
    return "35_54"


# ---------------------------------------------------------------------------
# Recommendation generation (no tools — pure LLM reasoning over numbers)
# ---------------------------------------------------------------------------
_REC_SYSTEM = """You are a financial advisor giving concise, specific recommendations to small business owners.
Be direct and cite the numbers. Begin your response with one of these three verdicts — choose based on the data:

  PROCEED       — revenue and profit both improve, margin holds or improves, confidence ≥ 65%
  PROCEED WITH CAUTION — mixed signals: revenue up but margin declines, OR low confidence (< 65%), OR sentiment negative
  DO NOT PROCEED — profit declines, margin drops significantly (> 5pp), or break-even > 60 months

Do not default to "proceed with caution" out of habit — use the thresholds above.
After the verdict, name the single most important risk in 1-2 sentences."""


def generate_recommendation(op1: dict, op2: dict, use_case: str, business_name: str) -> str | None:
    """
    Simulation Agent entry point for recommendation generation.
    Returns 2-3 sentence plain-English verdict grounded in OP1 → OP2 deltas.
    """
    f1    = op1.get("financials", {})
    f2    = op2.get("financials", {})
    delta = op2.get("delta", {})
    risk  = op2.get("risk", {})

    print(f"[simulation_agent] Generating recommendation for '{business_name}'...")

    result = run_agent(
        system_prompt=_REC_SYSTEM,
        user_message=(
            f"Business: {business_name}\n"
            f"Decision type: {use_case.replace('_', ' ')}\n\n"
            "Simulation results:\n"
            f"  Revenue:      ${f1.get('revenue', 0):,.0f} → ${f2.get('revenue', 0):,.0f}"
            f"  ({delta.get('revenue_delta', 0):+,.0f}/mo)\n"
            f"  Profit:       ${f1.get('profit', 0):,.0f} → ${f2.get('profit', 0):,.0f}"
            f"  ({delta.get('profit_delta', 0):+,.0f}/mo)\n"
            f"  Margin:       {f1.get('margin', 0)*100:.1f}% → {f2.get('margin', 0)*100:.1f}%\n"
            f"  Foot traffic: {f1.get('footfall', 0):,.0f} → {f2.get('footfall', 0):,.0f} visits/mo\n"
            f"  Confidence:   {risk.get('confidence_score', 0)*100:.0f}%\n"
            f"  Sentiment:    {risk.get('sentiment_score', 0):.2f}\n\n"
            "Write 2-3 sentences. Start with PROCEED, PROCEED WITH CAUTION, or DO NOT PROCEED "
            "based on whether the numbers justify it — do not hedge if the data is clearly positive or clearly negative. "
            "Cite the key numbers, then name the single most important risk."
        ),
    )

    text = (result or "").strip()
    if text:
        print(f"[simulation_agent] Recommendation generated ({len(text)} chars)")
    return text or None
