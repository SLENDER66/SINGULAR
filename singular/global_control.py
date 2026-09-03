from __future__ import annotations

from dataclasses import dataclass

from .agents import Commander
from .autopilot import ActionRequest, Autonomy, Governor
from .coherence import CoherenceReport, GlobalCoherenceGuard
from .collective_intelligence import CollectiveIntelligence, Deliberation, SharedSignal
from .models import Action, Risk
from .security import ActionPolicy
from .state import CapacityEngine, CapacitySnapshot
from .trajectory import TrajectoryAssessment, TrajectoryDecision, TrajectoryEngine, TrajectoryProfile
from .values import ValueAssessment, ValueAssessmentResult, ValueMode
from .world_model import EpistemicType, WorldModel
from .v32_governed_core import RedTeamFinding, RedTeamGate


@dataclass(frozen=True)
class GlobalDecisionReport:
    """Read-only cross-domain decision gate; never an authorization boundary."""

    objective: str
    action_id: str
    decision: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    capacity_recommendation: str | None
    policy_tier: str
    policy_requires_human: bool
    governor_mode: Autonomy
    red_team_findings: tuple[RedTeamFinding, ...]
    coherence: CoherenceReport | None
    deliberation: Deliberation | None = None
    trajectory: TrajectoryAssessment | None = None

    @property
    def can_prepare(self) -> bool:
        return not self.blockers and self.policy_tier != "BLACK"

    @property
    def requires_human(self) -> bool:
        return bool(self.warnings) or self.policy_requires_human or self.governor_mode is Autonomy.ESCALATE or (self.deliberation is not None and self.deliberation.unresolved) or (self.trajectory is not None and self.trajectory.human_review)


class GlobalDecisionGate:
    """Integrate mission, collective cognition, trajectory, context, risk and governance."""

    def __init__(self, commander: Commander | None = None, red_team: RedTeamGate | None = None, coherence_guard: GlobalCoherenceGuard | None = None, collective_intelligence: CollectiveIntelligence | None = None) -> None:
        self.commander = commander or Commander()
        self.red_team = red_team or RedTeamGate()
        self.coherence_guard = coherence_guard
        self.collective_intelligence = collective_intelligence or CollectiveIntelligence()

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
        shared_signals: tuple[SharedSignal, ...] = (),
        calibration: dict[str, float] | None = None,
        trajectory_profile: TrajectoryProfile | None = None,
        trajectory_dimensions: dict[str, float] | None = None,
    ) -> GlobalDecisionReport:
        blockers: list[str] = []
        warnings: list[str] = []
        coherence = None
        deliberation = None
        trajectory = None
        value_results = values or []

        if shared_signals:
            deliberation = self.collective_intelligence.deliberate(action.id, shared_signals, calibration=calibration)
            if deliberation.unresolved:
                warnings.append("COLLECTIVE:UNRESOLVED_DELIBERATION")
            if deliberation.blocking_challenges:
                blockers.extend(f"COLLECTIVE:CRITICAL_CHALLENGE:{claim}" for claim in deliberation.blocking_challenges)

        if trajectory_profile is not None:
            if trajectory_dimensions is None:
                warnings.append("TRAJECTORY:MISSING_DIMENSIONS")
                trajectory = TrajectoryAssessment(TrajectoryDecision.REVIEW, 0.0, 0.0, ("INSUFFICIENT_TRAJECTORY_DATA",), True)
            else:
                trajectory = TrajectoryEngine.assess(trajectory_profile, dimensions=trajectory_dimensions, value_results=tuple(value_results), capacity=capacity)
                if trajectory.decision is TrajectoryDecision.BLOCK:
                    blockers.extend(f"TRAJECTORY:{reason}" for reason in trajectory.rationale)
                elif trajectory.decision is TrajectoryDecision.REVIEW:
                    warnings.append("TRAJECTORY:REVIEW")

        if self.coherence_guard is not None:
            coherence = self.coherence_guard.inspect(mission_id)
            if not coherence.coherent:
                blockers.extend(f"COHERENCE:{code}" for code in coherence.blockers)

        if world_model is not None:
            if world_model.unknowns():
                warnings.append("WORLD_MODEL:UNKNOWN_REQUIRES_HUMAN_REVIEW")
            if world_model.objectives and not any(fact.epistemic in {EpistemicType.OBJECTIVE, EpistemicType.FACT, EpistemicType.ESTIMATE} for fact in world_model.objectives.values()):
                warnings.append("WORLD_MODEL:NO_QUALIFIED_OBJECTIVE")

        hard_value_violations = [v.value.name for v in value_results if v.assessment is ValueAssessment.VIOLATED and v.value.mode is ValueMode.HARD_CONSTRAINT]
        tradeoff_violations = [v.value.name for v in value_results if v.assessment is ValueAssessment.VIOLATED and v.value.mode is not ValueMode.HARD_CONSTRAINT]
        if hard_value_violations:
            blockers.append("VALUES:HARD_CONSTRAINT_VIOLATED:" + ",".join(hard_value_violations))
        if tradeoff_violations:
            warnings.append("VALUES:TRADEOFF_REQUIRES_EXPLICIT_REVIEW:" + ",".join(tradeoff_violations))
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

        commander_action = Action(id=action.id, name=action.name, impact=max(0.0, min(10.0, action.impact)), urgency=5.0, leverage=5.0, effort=max(0.001, min(10.0, effort if effort is not None else 1.0)), risk=action.risk, reversibility=action.reversibility)
        brief = self.commander.command(objective, [commander_action], capacity=capacity, effort=effort)
        if brief["mode"] == "CAPACITY_LIMIT":
            warnings.append("COMMANDER:CAPACITY_LIMIT")

        if not policy.can_prepare:
            blockers.extend(f"POLICY:{reason}" for reason in policy.reasons)
        if governor.mode is Autonomy.BLOCK:
            blockers.extend(f"GOVERNOR:{reason}" for reason in governor.reasons)

        decision = "BLOCK" if blockers else ("REVIEW" if warnings or policy.requires_human else "PROCEED")
        return GlobalDecisionReport(objective=objective, action_id=action.id, decision=decision, blockers=tuple(dict.fromkeys(blockers)), warnings=tuple(dict.fromkeys(warnings)), capacity_recommendation=capacity_decision, policy_tier=policy.tier.value, policy_requires_human=policy.requires_human, governor_mode=governor.mode, red_team_findings=findings, coherence=coherence, deliberation=deliberation, trajectory=trajectory)
