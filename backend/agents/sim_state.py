"""
SimState — shared state object that flows through the TwinTrack agent pipeline.

Every agent reads from and writes to a single SimState instance rather than
passing raw dicts between functions. This makes the pipeline:
  - Auditable: agent_log records exactly what each agent did and why
  - Testable:  any stage can be inspected or mocked in isolation
  - Readable:  orchestrator reads like a sequence of named steps

Lifecycle:
    orchestrator creates SimState → agents mutate it → to_response() serializes it

API response format stays backward-compatible — agent_log is additive.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Agent contribution record ─────────────────────────────────────────────────

@dataclass
class AgentContribution:
    """Records what one agent did at one step in the pipeline."""
    agent:       str            # e.g. "elasticity_agent", "critique_agent"
    action:      str            # e.g. "calibrated", "flagged", "recommended"
    notes:       str            # human-readable explanation of what was done
    adjustments: dict[str, Any] = field(default_factory=dict)
    # Optional: any quantitative changes the agent made
    # e.g. {"price_elasticity": {"before": -1.8, "after": -1.2}}


# ── SimState ──────────────────────────────────────────────────────────────────

@dataclass
class SimState:
    """
    Carries all inputs, intermediate results, and agent outputs through the
    TwinTrack pipeline.

    Populated progressively:
        twin, ip1, ip2  → set by orchestrator at start
        ms              → set after ML layer runs
        op1, op2        → set after sim_layer runs
        recommendation  → set by Simulation Agent
        use_case        → set from ip2
    """

    # ── Inputs ────────────────────────────────────────────────────────────────
    twin:     dict[str, Any] = field(default_factory=dict)  # enrolled business twin layer
    ip1:      dict[str, Any] = field(default_factory=dict)  # current-state financials
    ip2:      dict[str, Any] = field(default_factory=dict)  # proposed scenario params

    # ── ML layer output ───────────────────────────────────────────────────────
    ms:       dict[str, Any] = field(default_factory=dict)  # market snapshot

    # ── Simulation outputs ────────────────────────────────────────────────────
    op1:      dict[str, Any] = field(default_factory=dict)  # control (no change)
    op2:      dict[str, Any] = field(default_factory=dict)  # experiment (change applied)

    # ── Final outputs ─────────────────────────────────────────────────────────
    recommendation: str | None = None
    use_case:       str        = ""

    # ── Agent audit log ───────────────────────────────────────────────────────
    agent_log: list[AgentContribution] = field(default_factory=list)

    # ── Convenience helpers ───────────────────────────────────────────────────

    def log(
        self,
        agent:       str,
        action:      str,
        notes:       str,
        adjustments: dict[str, Any] | None = None,
    ) -> None:
        """Append an entry to the agent audit log."""
        self.agent_log.append(AgentContribution(
            agent=agent,
            action=action,
            notes=notes,
            adjustments=adjustments or {},
        ))

    def apply_confidence_adjustment(self, delta: float, reason: str) -> None:
        """
        Adjust op2's confidence_score by delta (positive or negative).
        Clamps result to [0.0, 1.0] and logs the change.
        """
        risk = self.op2.get("risk", {})
        before = float(risk.get("confidence_score", 0.5))
        after  = round(max(0.0, min(1.0, before + delta)), 4)
        risk["confidence_score"] = after
        self.op2["risk"] = risk
        self.log(
            agent="critique_agent",
            action="confidence_adjusted",
            notes=reason,
            adjustments={"confidence_score": {"before": before, "after": after, "delta": delta}},
        )

    def add_risk_flag(self, flag: dict[str, str]) -> None:
        """
        Append a flag dict to op2.risk.flags.
        Expected shape: {headline, relevance, impact}
        """
        risk  = self.op2.get("risk", {})
        flags = risk.get("flags", [])
        flags.append(flag)
        risk["flags"] = flags
        self.op2["risk"] = risk

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_response(self) -> dict[str, Any]:
        """
        Serialize to the API response dict.

        Backward-compatible with the existing frontend contract:
            {op1, op2, recommendation, use_case}

        Adds agent_log as an extra field — the frontend can ignore it for now
        but it's available for debugging, dashboards, and paper writeups.
        """
        return {
            "op1":            self.op1,
            "op2":            self.op2,
            "recommendation": self.recommendation,
            "use_case":       self.use_case,
            "agent_log": [
                {
                    "agent":       c.agent,
                    "action":      c.action,
                    "notes":       c.notes,
                    "adjustments": c.adjustments,
                }
                for c in self.agent_log
            ],
        }
