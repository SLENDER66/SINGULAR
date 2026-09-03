from __future__ import annotations

from dataclasses import dataclass

from .agents import Commander
from .autopilot import ActionRequest, Autonomy, Governor
from .coherence import CoherenceReport, GlobalCoherenceGuard
from .models import Action, Risk
from .security import ActionPolicy
from .state import CapacityEngine, CapacitySnapshot
from .values import ValueAssessment, ValueAssessmentResult
from .world_model import EpistemicType, WorldModel
from .v32_governed_core import RedTeamFinding, RedTeamGate


@dataclass(frozen=True)
class GlobalDecisionReport:
    """Read-only cross-domain decision gate.

    This layer integrates context; it does not grant authority and never
    executes an external action. Governance remains the final authorization
    boundary and system changes remain separately controlled.
    """

    objective: str
    action_id: str
    decision: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    capacity_recommendation: str | None
    policy_tier: str
    governor_mode: Autonomy
    red_team_findings: tuple[RedTeamFinding, ...]
    coherence: CoherenceReport | None

    @property
    def can_prepare(self) -> bool:
        return not self.blockers and self.policy_tier != "BLACK"

    @property
    def requires_human(self) -> bool:
        return bool(self.warnings) or self.governor_mode is Autonomy.ESCALATE


class GlobalDecisionGate:
    """Integrate mission, world model, values, capacity, risk and governance."""

    def __init__(
        self,
        commander: Commander | None = None,
        red_team: RedTeamGate | None = None,
        coherence_guard: GlobalCoherenceGuard | None = None,
    ) -> None:
        self.commander = commander or Commander()
        self.red_team = red_team or RedTeamGate()
        self.coherence_guard = coherence_guard

    def evaluate(
        self,
        objective: str,
        action: ActionRequest,
        *,
        world_model: WorldModel | None = None,
        values: list[ValueAssessmentResult] | None = None,
        capacity: CapacitySnapshot | None = None,
        effort: float | None = None,
        risks: list[Risk] | None = None,
        mission_id: str | None = None,
    ) -> GlobalDecisionReport:
        blockers: list[str] = []
        warnings: list[str] = []
        coherence = None

        if self.coherence_guard is not None:
            coherence = self.coherence_guard.inspect(mission_id)
            if not coherence.coherent:
                blockers.extend(f"COHERENCE:{code}" for code in coherence.blockers)

        if world_model is not None:
            if world_model.unknowns():
                warnings.append("WORLD_MODEL:UNKNOWN_REQUIRES_HUMAN_REVIEW")
            if world_model.objectives and not any(
                fact.epistemic in {EpistemicType.OBJECTIVE, EpistemicType.FACT, EpistemicType.ESTIMATE}
                for fact in world_model.objectives.values()
            ):
                warnings.append("WORLD_MODEL:NO_QUALIFIED_OBJECTIVE")

        value_results = values or []
        if any(v.assessment is ValueAssessment.VIOLATED for v in value_results):
            blockers.append("VALUES:VIOLATED")
        if any(v.assessment is ValueAssessment.UNKNOWN for v in value_results):
            warnings.append("VALUES:UNKNOWN_REQUIRES_HUMAN_REVIEW")
        if any(v.assessment is ValueAssessment.TENSION for v in value_results):
            warnings.append("VALUES:TENSION")

        capacity_decision = None
        if capacity is not None and effort is not None:
            capacity_decision = CapacityEngine.recommendation(capacity, effort)
            if capacity_decision == "DEFER_OR_DROP":
                blockers.append("CAPACITY:DEFER_OR_DROP")
            elif capacity_decision in {"REDUCE_SCOPE", "CLARIFY_STATE"}:
                warnings.append(f"CAPACITY:{capacity_decision}")

        for risk in risks or []:
            exposure = risk.probability * risk.impact
            if exposure >= 8 and risk.reversibility <= 2:
                blockers.append(f"RISK:HIGH_EXPOSURE:{risk.id}")
            elif exposure >= 5:
                warnings.append(f"RISK:ELEVATED:{risk.id}")

        policy = ActionPolicy.evaluate(action)
        governor = Governor.evaluate(action, None)
        findings = self.red_team.inspect(action, None)
        if any(f.blocking for f in findings):
            blockers.extend(f"RED_TEAM:{f.statement}" for f in findings if f.blocking)

        commander_action = Action(
            id=action.id,
            name=action.name,
            impact=max(0.0, min(10.0, action.impact)),
            urgency=5.0,
            leverage=5.0,
            effort=max(0.001, min(10.0, effort if effort is not None else 1.0)),
            risk=action.risk,
            reversibility=action.reversibility,
        )
        brief = self.commander.command(
            objective,
            [commander_action],
            capacity=capacity,
            effort=effort,
        )
        if brief["mode"] == "CAPACITY_LIMIT":
            warnings.append("COMMANDER:CAPACITY_LIMIT")

        if not policy.can_prepare:
            blockers.extend(f"POLICY:{reason}" for reason in policy.reasons)
        if governor.mode is Autonomy.BLOCK:
            blockers.extend(f"GOVERNOR:{reason}" for reason in governor.reasons)

        decision = "BLOCK" if blockers else ("REVIEW" if warnings or policy.requires_human else "PROCEED")
        return GlobalDecisionReport(
            objective=objective,
            action_id=action.id,
            decision=decision,
            blockers=tuple(dict.fromkeys(blockers)),
            warnings=tuple(dict.fromkeys(warnings)),
            capacity_recommendation=capacity_decision,
            policy_tier=policy.tier.value,
            governor_mode=governor.mode,
            red_team_findings=findings,
            coherence=coherence,
        )
