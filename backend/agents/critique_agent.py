"""
Critique Agent — post-simulation ReAct loop that checks OP1→OP2 projections
against the market snapshot for contradictions.

Pattern: Reason → Act (apply_penalty / flag_finding) → Reason → done

The agent receives the simulation output and the MS economic signals, then:
  1. Identifies contradictions between projected outcomes and macro context
  2. Calls flag_finding for each contradiction found
  3. Calls apply_penalty if the contradictions justify a confidence reduction
  4. Returns a structured critique summary

The orchestrator uses the agent output to mutate SimState (apply confidence
adjustment, add risk flags) — the math stays in Python, not in the LLM.
"""
from __future__ import annotations

import json
import sys
import os

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from agents.base import run_agent

# ── Tools the agent can call ──────────────────────────────────────────────────

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "flag_finding",
            "description": (
                "Record a specific contradiction or risk found between the "
                "simulation projection and the market context. Call once per finding."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "headline": {
                        "type": "string",
                        "description": "Short label for the finding (e.g. 'Rising CPI conflicts with revenue growth')",
                    },
                    "relevance": {
                        "type": "string",
                        "description": "Why this matters for the specific use case and business",
                    },
                    "impact": {
                        "type": "string",
                        "enum": ["positive", "negative", "neutral"],
                        "description": "Direction of impact on the projection reliability",
                    },
                },
                "required": ["headline", "relevance", "impact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_penalty",
            "description": (
                "Apply a confidence score reduction (0.0 to 0.3) based on the "
                "severity of contradictions found. Only call if you found at least "
                "one significant contradiction. Do not call for minor risks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "Penalty amount between 0.05 and 0.30",
                    },
                    "reason": {
                        "type": "string",
                        "description": "One sentence explaining why this penalty is warranted",
                    },
                },
                "required": ["amount", "reason"],
            },
        },
    },
]

_SYSTEM = """You are a simulation quality analyst reviewing a financial projection for a small business.

Your job:
1. Review the simulation output (OP1 baseline → OP2 proposed change)
2. Check each projection against the economic signals in the market snapshot
3. Flag contradictions — cases where the projection seems inconsistent with the market context
4. Apply a confidence penalty only if you find significant contradictions

Contradictions to check for:
- Revenue growth projected despite negative market sentiment (sentiment_score < -0.3)
- Price increase proposed while CPI is rising and customers are already price-sensitive
- Large margin improvement while labor costs are high (labor_elasticity > 1.5)
- Strong audience growth projected when that demographic has low income share
- Franchising expansion projected during high interest rates
- Any use-case projection that conflicts with sector_consumer_spending trend

Be analytical, not pessimistic. If the projection looks sound, say so and do not apply a penalty.
Call flag_finding for each real issue you find (0 to 3 findings).
Call apply_penalty once at the end only if warranted (omit if projection is sound).
After tool calls, reply with a one-sentence verdict."""


def _make_tool_state() -> tuple[list[dict], float | None, str]:
    """Returns (findings list, penalty_amount, penalty_reason) — mutable via closure."""
    findings      = []
    penalty       = [None]   # list so closure can mutate
    penalty_reason = [""]

    def flag_finding(headline: str, relevance: str, impact: str) -> dict:
        findings.append({"headline": headline, "relevance": relevance, "impact": impact})
        print(f"[critique_agent] Finding: {headline}")
        return {"recorded": True, "total_findings": len(findings)}

    def apply_penalty(amount: float, reason: str) -> dict:
        clamped = round(max(0.05, min(0.30, float(amount))), 2)
        penalty[0] = clamped
        penalty_reason[0] = reason
        print(f"[critique_agent] Penalty: -{clamped} — {reason}")
        return {"applied": True, "amount": clamped}

    tool_fns = {
        "flag_finding":  flag_finding,
        "apply_penalty": apply_penalty,
    }
    return findings, penalty, penalty_reason, tool_fns


def critique_simulation(state: "SimState") -> dict:
    """
    Critique Agent entry point.

    Reads ms, ip1, ip2, op1, op2 from state.
    Returns critique dict:
        {
            findings:   [{headline, relevance, impact}],
            penalty:    float | None,
            rationale:  str,
            verdict:    str,
        }
    Does NOT mutate state — the orchestrator applies the results.
    """
    from agents.sim_state import SimState  # local import avoids circular

    ms   = state.ms
    ip1  = state.ip1
    ip2  = state.ip2
    op1  = state.op1
    op2  = state.op2

    use_case = ip2.get("use_case", "")

    # ── Build economic signal summary for the prompt ──────────────────────────
    econ  = ms.get("economic_indicators", {})
    news  = ms.get("news_context", {})
    elast = ms.get("elasticity_modifiers", {})
    demo  = ms.get("demographic_data", {})

    def _sig(key: str) -> str:
        ind = econ.get(key, {})
        return f"{ind.get('current', 'N/A')} (trend: {ind.get('trend', 'unknown')})"

    cpi_trend     = econ.get("cpi", {}).get("trend", "unknown")
    unemp_trend   = econ.get("unemployment", {}).get("trend", "unknown")
    sector_trend  = econ.get("sector_consumer_spending", {}).get("trend", "unknown")
    sentiment     = float(news.get("sentiment_score", 0.0))
    labor_elast   = float(elast.get("labor_elasticity", 1.0))
    price_elast   = float(elast.get("price_elasticity", -1.0))

    f1     = op1.get("financials", {})
    f2     = op2.get("financials", {})
    delta  = op2.get("delta", {})
    risk   = op2.get("risk", {})

    rev_delta_pct = (
        round((f2.get("revenue", 0) - f1.get("revenue", 0)) / max(f1.get("revenue", 1), 1) * 100, 1)
        if f1.get("revenue") else 0
    )

    income_dist  = demo.get("income_distribution", {})
    above_100k   = float(income_dist.get("above_100k", 0.2))

    # ── Use-case-specific parameters summary ─────────────────────────────────
    if use_case == "pricing":
        scenario_summary = (
            f"Price change: {round(float(ip2.get('price_change_pct', 0)) * 100, 1)}%\n"
            f"Price elasticity: {price_elast}"
        )
    elif use_case == "target_audience":
        target_demo = ip2.get("target_demographic", ip2.get("audience_shift", "unknown"))
        mkt_budget  = round(float(ip2.get("marketing_spend_pct", 0)) * 100, 1)
        scenario_summary = (
            f"Target demographic: {target_demo}\n"
            f"Marketing budget: {mkt_budget}% of revenue\n"
            f"High-income share in this MSA: {round(above_100k * 100, 1)}%"
        )
    elif use_case == "franchising":
        scenario_summary = (
            f"New locations: {ip2.get('new_locations', 1)}\n"
            f"Investment/location: ${float(ip2.get('investment_per_location', 0)):,.0f}\n"
            f"Interest rate trend: {econ.get('interest_rate', {}).get('trend', 'unknown')}"
        )
    else:
        scenario_summary = f"Use case: {use_case}"

    # ── Build the user message ────────────────────────────────────────────────
    user_message = f"""Business simulation critique request

Use case: {use_case.replace('_', ' ')}
Business: {(state.twin.get("meta") or {}).get("business_name", "Unknown")}

SCENARIO
{scenario_summary}

SIMULATION OUTPUT
  Baseline revenue:  ${f1.get('revenue', 0):,.0f}/mo
  Projected revenue: ${f2.get('revenue', 0):,.0f}/mo  ({rev_delta_pct:+.1f}%)
  Profit delta:      ${delta.get('profit_delta', 0):+,.0f}/mo
  Margin:            {f1.get('margin', 0)*100:.1f}% → {f2.get('margin', 0)*100:.1f}%
  Confidence score:  {risk.get('confidence_score', 0.5):.2f}

MARKET CONTEXT
  CPI:                     {_sig("cpi")}
  Unemployment:            {_sig("unemployment")}
  Sector spending:         {_sig("sector_consumer_spending")}
  Interest rate:           {_sig("interest_rate")}
  Market sentiment:        {sentiment:.2f}  (-1=very negative, +1=very positive)
  Labor elasticity:        {labor_elast}  (>1.5 = expensive/scarce labor)
  Market saturation:       {elast.get("market_elasticity", 0.5)}

Check for contradictions. Call flag_finding for each issue found (max 3).
Call apply_penalty only if contradictions are significant.
Then give a one-sentence verdict."""

    # ── Run agent ─────────────────────────────────────────────────────────────
    findings, penalty, penalty_reason, tool_fns = _make_tool_state()

    print("[critique_agent] Reviewing simulation output for contradictions...")

    try:
        verdict = run_agent(
            system_prompt=_SYSTEM,
            user_message=user_message,
            tools=_TOOLS,
            tool_functions=tool_fns,
            max_iterations=6,
        )
    except Exception as e:
        print(f"[critique_agent] Agent failed ({e}) — skipping critique")
        return {"findings": [], "penalty": None, "rationale": "", "verdict": ""}

    verdict_text = (verdict or "").strip()
    print(f"[critique_agent] Verdict: {verdict_text[:120]}")

    return {
        "findings":  findings,
        "penalty":   penalty[0],
        "rationale": penalty_reason[0],
        "verdict":   verdict_text,
    }
