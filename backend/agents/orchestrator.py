"""
Orchestrator — coordinates TwinTrack's multi-agent pipeline.

The orchestrator is a Python coordinator (not an LLM). It delegates each
LLM-dependent task to the right agent and hands outputs to the next stage.

Pipeline for a simulation request:
  1. Enrichment Agent  → parse NL description into structured IP2 params
  2. Simulation engine → run_simulation(ms, ip1, ip2)  [existing sim_layer.py]
  3. Simulation Agent  → generate plain-English recommendation from OP deltas

Context/sentiment/forecast work happens inside the ML layer (ml/main.py) and
is already orchestrated there — the agents replace only the LLM calls within
that layer (see context.py and sentiment.py).
"""
import sys
import os

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SIM_DIR  = os.path.join(_BACKEND, "sim")
_ML_DIR   = os.path.join(_BACKEND, "ml")
for _p in [_BACKEND, _SIM_DIR, _ML_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from agents.enrichment_agent import extract_nl_parameters
from agents.simulation_agent import generate_recommendation
from main import build_market_snapshot
from sim_bridge import ui_sim_to_ip2


def run_pipeline(
    twin: dict,
    ip1: dict,
    ip2: dict,
    ms: dict,
    nl_description: str = "",
) -> dict:
    """
    Full orchestration pipeline.

    Args:
        twin:           enrolled business twin_layer dict
        ip1:            current-state IP dict
        ip2:            proposed-scenario IP dict (may be enriched by NL)
        ms:             market snapshot produced by the ML layer
        nl_description: optional free-text from the UI simulation form

    Returns:
        {"op1": ..., "op2": ..., "recommendation": ...}
    """
    from sim_layer import run_simulation

    print("[orchestrator] ── Starting multi-agent pipeline ──────────────────")

    # ── Step 1: Enrichment Agent ─────────────────────────────────────────────
    # If the user typed a natural-language description, extract any explicit
    # parameter overrides and merge them into IP2 before running the simulation.
    if nl_description and nl_description.strip():
        print("[orchestrator] → Enrichment Agent: extracting NL parameters...")
        ip2 = extract_nl_parameters(nl_description, ip2.get("use_case", ""), ip2)

    # ── Step 2: Simulation engine ────────────────────────────────────────────
    # Existing rules-based financial simulator — no LLM involved.
    print("[orchestrator] → Simulation engine: running financial simulation...")
    op = run_simulation(ms, ip1, ip2)

    # ── Step 3: Simulation Agent ─────────────────────────────────────────────
    # Generate a plain-English recommendation grounded in the OP1 → OP2 deltas.
    business_name = str((twin.get("meta") or {}).get("business_name") or "Business")
    print("[orchestrator] → Simulation Agent: generating recommendation...")
    recommendation = generate_recommendation(
        op["op1"], op["op2"], ip2.get("use_case", ""), business_name
    )

    print("[orchestrator] ── Pipeline complete ────────────────────────────────")
    return {
        "op1": op["op1"],
        "op2": op["op2"],
        "recommendation": recommendation,
    }


def run_simulate_pipeline(
    twin: dict,
    ip1: dict,
    sim_params: dict,
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
        { "op1": ..., "op2": ..., "recommendation": ..., "use_case": ... }
    """
    print("[orchestrator] ── Starting simulate pipeline ───────────────────────")

    # ── Step 1: Build IP2 from frontend sim params ───────────────────────────
    monthly_revenue = float(ip1.get("monthly_revenue") or 0)
    ip2 = ui_sim_to_ip2(sim_params, monthly_revenue)
    print(f"[orchestrator] → IP2 built: use_case={ip2.get('use_case')}")

    # ── Step 2: ML layer — fetch live data + build market snapshot ───────────
    print("[orchestrator] → ML layer: building market snapshot from live APIs...")
    ms = build_market_snapshot(twin)

    # ── Step 3: Run the core agent pipeline (enrich → simulate → recommend) ──
    result = run_pipeline(twin, ip1, ip2, ms, nl_description)

    result["use_case"] = ip2.get("use_case", sim_params.get("useCase", "pricing"))
    print("[orchestrator] ── Simulate pipeline complete ────────────────────────")
    return result
