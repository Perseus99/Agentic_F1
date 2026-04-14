"""
Orchestrator — coordinates TwinTrack's multi-agent pipeline.

The orchestrator creates a SimState at the start and passes it through every
agent. Each agent reads what it needs from state and writes its output back.
The final state.to_response() produces the API-compatible result.

Pipeline (run_pipeline):
  1. Enrichment Agent   → enriches ip2 from NL description, logs to state
  2. Simulation engine  → runs rules-based financials, stores op1/op2 in state
  3. Critique Agent     → checks projections vs market context, adjusts confidence
  4. Simulation Agent   → generates recommendation from final op1/op2, stores in state

Context/sentiment/forecast/elasticity work happens inside the ML layer
(ml/main.py → elasticity_agent.py) and is already coordinated there.
"""
import sys
import os

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SIM_DIR  = os.path.join(_BACKEND, "sim")
_ML_DIR   = os.path.join(_BACKEND, "ml")
for _p in [_BACKEND, _SIM_DIR, _ML_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from agents.sim_state      import SimState
from agents.enrichment_agent  import extract_nl_parameters
from agents.critique_agent    import critique_simulation
from agents.simulation_agent  import generate_recommendation
from main        import build_market_snapshot
from sim_bridge  import ui_sim_to_ip2


def run_pipeline(
    twin:           dict,
    ip1:            dict,
    ip2:            dict,
    ms:             dict,
    nl_description: str = "",
) -> dict:
    """
    Full orchestration pipeline.

    Args:
        twin:           enrolled business twin_layer dict
        ip1:            current-state IP dict
        ip2:            proposed-scenario IP dict
        ms:             market snapshot produced by the ML layer
        nl_description: optional free-text from the UI simulation form

    Returns:
        API response dict — backward-compatible shape plus agent_log
        {op1, op2, recommendation, use_case, agent_log}
    """
    from sim_layer import run_simulation

    print("[orchestrator] ── Starting multi-agent pipeline ──────────────────")

    # ── Initialise SimState ──────────────────────────────────────────────────
    state          = SimState()
    state.twin     = twin
    state.ip1      = ip1
    state.ip2      = ip2
    state.ms       = ms
    state.use_case = ip2.get("use_case", "")

    # ── Step 1: Enrichment Agent ─────────────────────────────────────────────
    if nl_description and nl_description.strip():
        print("[orchestrator] → Enrichment Agent: extracting NL parameters...")
        enriched_ip2 = extract_nl_parameters(
            nl_description, state.ip2.get("use_case", ""), state.ip2
        )
        # Log what changed
        changed = {
            k: {"before": state.ip2[k], "after": enriched_ip2[k]}
            for k in state.ip2
            if k in enriched_ip2 and state.ip2[k] != enriched_ip2[k]
        }
        state.ip2 = enriched_ip2
        state.log(
            agent="enrichment_agent",
            action="enriched",
            notes=f"Extracted parameters from NL description: '{nl_description[:80]}'",
            adjustments=changed,
        )
    else:
        state.log(
            agent="enrichment_agent",
            action="skipped",
            notes="No NL description provided — using form parameters as-is",
        )

    # ── Step 2: Simulation engine ────────────────────────────────────────────
    print("[orchestrator] → Simulation engine: running financial simulation...")
    sim_result  = run_simulation(ms, state.ip1, state.ip2)
    state.op1   = sim_result["op1"]
    state.op2   = sim_result["op2"]
    state.log(
        agent="simulation_engine",
        action="simulated",
        notes=(
            f"Rules-based simulation complete. "
            f"Revenue: ${state.op1['financials']['revenue']:,.0f} → "
            f"${state.op2['financials']['revenue']:,.0f}/mo"
        ),
    )

    # ── Step 3: Critique Agent ───────────────────────────────────────────────
    print("[orchestrator] → Critique Agent: checking projections vs market context...")
    critique = critique_simulation(state)

    # Apply findings as risk flags
    for finding in critique.get("findings", []):
        state.add_risk_flag(finding)

    # Apply confidence penalty if agent warranted one
    if critique.get("penalty") is not None:
        state.apply_confidence_adjustment(
            delta  = -critique["penalty"],
            reason = critique.get("rationale", "Critique Agent penalty"),
        )

    # Log critique summary
    n_findings = len(critique.get("findings", []))
    verdict    = critique.get("verdict", "")
    state.log(
        agent="critique_agent",
        action="critiqued",
        notes=(
            f"{n_findings} finding(s). "
            + (f"Penalty: -{critique['penalty']:.2f}. " if critique.get("penalty") else "No penalty. ")
            + (verdict[:120] if verdict else "")
        ),
        adjustments={
            "findings_count": n_findings,
            "penalty_applied": critique.get("penalty"),
        },
    )

    # ── Step 4: Simulation Agent ─────────────────────────────────────────────
    business_name = str((twin.get("meta") or {}).get("business_name") or "Business")
    print("[orchestrator] → Simulation Agent: generating recommendation...")
    recommendation = generate_recommendation(
        state.op1, state.op2, state.ip2.get("use_case", ""), business_name
    )
    state.recommendation = recommendation
    state.log(
        agent="simulation_agent",
        action="recommended",
        notes=f"Recommendation generated ({len(recommendation or '')} chars)",
    )

    print("[orchestrator] ── Pipeline complete ────────────────────────────────")
    return state.to_response()


def run_simulate_pipeline(
    twin:           dict,
    ip1:            dict,
    sim_params:     dict,
    nl_description: str = "",
) -> dict:
    """
    Entry point for the /api/simulate HTTP endpoint.
    Coordinates the full pipeline from raw frontend sim params to final output.

    Args:
        twin:           enrolled business twin_layer dict
        ip1:            pre-computed IP1 from enrollment record
        sim_params:     raw sim object from the frontend
                        { useCase, priceChangePct, audienceShift,
                          marketingBudgetPct, franchiseFee, newLocations, ... }
        nl_description: optional free-text from the UI NL description field

    Returns:
        { op1, op2, recommendation, use_case, agent_log }
    """
    print("[orchestrator] ── Starting simulate pipeline ───────────────────────")

    # ── Step 1: Build IP2 from frontend sim params ───────────────────────────
    monthly_revenue = float(ip1.get("monthly_revenue") or 0)
    ip2 = ui_sim_to_ip2(sim_params, monthly_revenue)
    print(f"[orchestrator] → IP2 built: use_case={ip2.get('use_case')}")

    # ── Step 2: ML layer — fetch live data + build market snapshot ───────────
    print("[orchestrator] → ML layer: building market snapshot from live APIs...")
    ms = build_market_snapshot(twin)

    # ── Step 3: Run the core agent pipeline ──────────────────────────────────
    result = run_pipeline(twin, ip1, ip2, ms, nl_description)

    # Ensure use_case is present (run_pipeline sets it but be defensive)
    result["use_case"] = ip2.get("use_case", sim_params.get("useCase", "pricing"))
    print("[orchestrator] ── Simulate pipeline complete ────────────────────────")
    return result
