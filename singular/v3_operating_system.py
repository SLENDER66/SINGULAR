from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from uuid import uuid4
from datetime import datetime, timezone

from .autopilot import ActionRequest, DelegationContract, ExecutionBus, Autonomy
from .models import WorldModel, Evidence, Certainty, Action, Decision, Learning
from .security import ActionPolicy, PolicyDecision
from .audit import AuditTrail


class SignalType(str, Enum):
    FACT = "FACT"
    CHANGE = "CHANGE"
    ALERT = "ALERT"
    OPPORTUNITY = "OPPORTUNITY"
    BLOCKER = "BLOCKER"


@dataclass(frozen=True)
class Signal:
    type: SignalType
    source: str
    statement: str
    confidence: float = 1.0
    impact: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    id: str = field(default_factory=lambda: "SIG-" + uuid4().hex[:10])


@dataclass(frozen=True)
class CandidateAction:
    name: str
    impact: float
    urgency: float
    leverage: float
    effort: float
    risk: float
    reversibility: float
    optionality: float = 5.0
    objective_id: str | None = None

    @property
    def score(self) -> float:
        upside = self.impact * 0.30 + self.urgency * 0.15 + self.leverage * 0.20 + self.optionality * 0.10
        friction = self.effort * 0.10 + self.risk * 0.10 + (10 - self.reversibility) * 0.05
        return round(upside - friction, 4)


@dataclass(frozen=True)
class DecisionAssessment:
    action: CandidateAction
    confidence: float
    recommendation: str
    red_team_flags: tuple[str, ...]
    needs_human: bool


class DecisionEngine:
    """Deterministic decision layer. It scores candidates, exposes uncertainty, and never executes."""
    def assess(self, candidates: list[CandidateAction], world: WorldModel) -> DecisionAssessment | None:
        if not candidates:
            return None
        ranked = sorted(candidates, key=lambda x: x.score, reverse=True)
        best = ranked[0]
        second = ranked[1] if len(ranked) > 1 else None
        confidence = min(1.0, max(0.0, 0.5 + (best.score - (second.score if second else best.score - 2.0)) / 10.0))
        flags: list[str] = []
        if best.risk >= 7:
            flags.append("Risque élevé")
        if best.reversibility <= 3:
            flags.append("Faible réversibilité")
        if not world.objectives and best.objective_id is None:
            flags.append("Aucun objectif explicite relié")
        if confidence < 0.60:
            flags.append("Confiance faible")
        needs_human = best.risk >= 8 or best.reversibility <= 2
        recommendation = "EXECUTE_OR_PREPARE" if not needs_human else "ESCALATE"
        return DecisionAssessment(best, round(confidence, 3), recommendation, tuple(flags), needs_human)


@dataclass
class ObservationCycle:
    signals: list[Signal]
    candidates: list[CandidateAction]
    assessment: DecisionAssessment | None
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class WorldModelUpdater:
    """Turns external/internal signals into explicit evidence without silently rewriting facts."""
    def apply(self, world: WorldModel, signals: list[Signal]) -> WorldModel:
        for signal in signals:
            certainty = Certainty.FACT if signal.type == SignalType.FACT else Certainty.HYPOTHESIS
            world.evidence.append(Evidence(
                id=signal.id,
                statement=signal.statement,
                certainty=certainty,
                source=signal.source,
                confidence=max(0.0, min(1.0, signal.confidence)),
            ))
        world.updated_at = datetime.now(timezone.utc).isoformat()
        return world


@dataclass(frozen=True)
class LearningRecord:
    hypothesis: str
    prediction: str
    actual: str
    error: float
    lesson: str
    confidence: float
    id: str = field(default_factory=lambda: "LRN-" + uuid4().hex[:10])


class LearningEngineV3:
    """Closes the forecast -> result -> lesson loop while keeping learning explicit."""
    def record(self, world: WorldModel, record: LearningRecord) -> Learning:
        learning = Learning(
            id=record.id,
            hypothesis=record.hypothesis,
            prediction=record.prediction,
            result=record.actual,
            lesson=record.lesson,
            confidence=max(0.0, min(1.0, record.confidence)),
        )
        world.learnings.append(learning)
        return learning


@dataclass(frozen=True)
class SystemChange:
    problem: str
    evidence: tuple[str, ...]
    modification: str
    expected_benefit: str
    risk: str
    test: str
    success_criteria: tuple[str, ...]
    rollback: str
    id: str = field(default_factory=lambda: "CHG-" + uuid4().hex[:10])


class SystemArchitectV3:
    """Proposes system changes; it does not silently self-modify."""
    def propose(self, problem: str, evidence: list[str], modification: str, expected_benefit: str,
                risk: str, test: str, success_criteria: list[str], rollback: str) -> SystemChange:
        return SystemChange(problem, tuple(evidence), modification, expected_benefit, risk, test, tuple(success_criteria), rollback)


@dataclass
class OperatingSnapshot:
    objective_count: int
    evidence_count: int
    opportunity_count: int
    risk_count: int
    learning_count: int
    pending_approvals: int
    next_action: str | None
    decision_confidence: float
    human_intervention_required: bool


class SingularV3:
    """Integrated operating layer: observe, model, decide, govern, learn, improve."""
    def __init__(self, world: WorldModel | None = None, execution_bus: ExecutionBus | None = None):
        self.world = world or WorldModel()
        self.updater = WorldModelUpdater()
        self.decisions = DecisionEngine()
        self.learning = LearningEngineV3()
        self.architect = SystemArchitectV3()
        self.bus = execution_bus or ExecutionBus()
        self.audit = AuditTrail()
        self.last_cycle: ObservationCycle | None = None

    def observe(self, signals: list[Signal]) -> list[Signal]:
        self.updater.apply(self.world, signals)
        return signals

    def decide(self, candidates: list[CandidateAction]) -> DecisionAssessment | None:
        assessment = self.decisions.assess(candidates, self.world)
        if assessment:
            d = Decision(
                id="DEC-" + uuid4().hex[:10],
                question="Quelle est la meilleure prochaine action ?",
                context="SINGULAR V3 decision cycle",
                options=[c.name for c in candidates],
                recommendation=assessment.action.name,
                confidence=assessment.confidence,
                red_team=list(assessment.red_team_flags),
                validation_required=assessment.needs_human,
            )
            self.world.decisions.append(d)
        return assessment

    def cycle(self, signals: list[Signal], candidates: list[CandidateAction]) -> ObservationCycle:
        self.observe(signals)
        assessment = self.decide(candidates)
        self.last_cycle = ObservationCycle(signals, candidates, assessment)
        return self.last_cycle

    def prepare_action(
        self,
        candidate: CandidateAction,
        mission_id: str | None = None,
        contract: DelegationContract | None = None,
    ):
        """Prepare/route an action without bypassing governance.

        If a contract is supplied, it is passed to the Governor. The V3 core does
        not invent authorization. A mission id is retained on the action for audit
        and correlation, but does not itself grant execution rights.
        """
        action = ActionRequest(
            name=candidate.name,
            description=f"SINGULAR V3 action: {candidate.name}",
            impact=candidate.impact,
            risk=candidate.risk,
            reversibility=candidate.reversibility,
            requires_human=candidate.risk >= 8 or candidate.reversibility <= 2,
            sensitive=False,
            contract_id=mission_id or (contract.mission_id if contract else None),
        )
        policy = ActionPolicy.evaluate(action)
        decision = self.bus.submit(action, contract)
        self.audit.record(
            "action_routing",
            "SINGULAR_V3",
            decision.mode.value,
            {"action_id": action.id, "policy_tier": policy.tier.value, "reasons": list(decision.reasons)},
        )
        return decision

    def snapshot(self) -> OperatingSnapshot:
        assessment = self.last_cycle.assessment if self.last_cycle else None
        return OperatingSnapshot(
            objective_count=len(self.world.objectives),
            evidence_count=len(self.world.evidence),
            opportunity_count=len(self.world.opportunities),
            risk_count=len(self.world.risks),
            learning_count=len(self.world.learnings),
            pending_approvals=len(self.bus.pending()),
            next_action=assessment.action.name if assessment else None,
            decision_confidence=assessment.confidence if assessment else 0.0,
            human_intervention_required=assessment.needs_human if assessment else False,
        )
