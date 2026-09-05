"""Shared fixtures for tests. Not a test module: it defines no test functions.

The pieces here exist because several suites need a decision that was *actually
executed*, not merely constructed. OutcomeLedger and everything built on it
(learning review queue, continuous learning, the control plane) require an
observation to name the execution key derived from the decision, backed by a
terminal execution row in the same database. Tests that invented an execution
key were rejected before reaching the behaviour they assert.
"""
from __future__ import annotations

from pathlib import Path

from singular.autopilot import ActionRequest, Autonomy, DelegationContract
from singular.decision_attestation import ValidatedDecisionIssuer
from singular.domain_learning import LearningDomain
from singular.durable import DurableStore
from singular.execution import DurableExecutionEngine
from singular.execution_capability import register_execution_capability
from singular.human_optimization import DomainState, Intervention
from singular.mission_runtime import DurableMissionRuntime
from singular.trajectory import TrajectoryProfile
from singular.validated_pipeline import ValidatedTrajectoryPipeline
from singular.validated_trajectory_decision import ValidatedTrajectoryDecision
from singular.values import Vision

#: Every invocation of the shared handler, so a suite can assert a replay did
#: not re-run it without passing an executable the boundary would reject.
HANDLER_CALLS: list[str] = []


def support_handler(action):
    HANDLER_CALLS.append(action.id)
    return {"action_id": action.id, "executed": True}


SUPPORT_HANDLER_CAPABILITY = register_execution_capability(support_handler, "cap_support_handler")


def build_decision(
    *,
    decision_id: str = "DEC-SUPPORT",
    mission_id: str = "MIS-SUPPORT",
    execution_target: str = SUPPORT_HANDLER_CAPABILITY,
) -> ValidatedTrajectoryDecision:
    """One executable decision through the full validated pipeline."""
    contract = DelegationContract(mission_id, "Improve career", "Career action completed",
                                  autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("career_test", "Run bounded career test", 4, 1, 9, contract_id=mission_id)
    state = DomainState(LearningDomain.CAREER, 0.2, confidence=0.9)
    intervention = Intervention("career", LearningDomain.CAREER, 0.9, evidence=0.9, causal_confidence=0.9, capacity=1)
    profile = TrajectoryProfile(Vision("Build a resilient long-term career"), money=1, time=1, capability=2,
                                energy=1, freedom=1, ownership=1, learning=2, resilience=1, transmission=1)
    dimensions = {name: 0.8 for name in profile.weights}
    return ValidatedTrajectoryPipeline.build(
        objective=contract.objective, actions=(action,),
        action_to_intervention=((action.id, intervention.id),),
        domain_states=(state,), interventions=(intervention,), trajectory_profile=profile,
        trajectory_dimensions=dimensions, contract=contract,
        execution_target=execution_target, decision_id=decision_id, capacity_budget=2,
    )


class ExecutedDecision:
    """A decision that was attested and run to a terminal state on one database."""

    def __init__(self, decision: ValidatedTrajectoryDecision, path: Path) -> None:
        self.decision = decision
        self.path = path
        self.runtime = DurableMissionRuntime(DurableStore(path))
        self.runtime.store.save_mission(decision.contract)
        self.engine = DurableExecutionEngine(self.runtime)
        ValidatedDecisionIssuer(self.engine.attestation_store).issue(decision)
        self.result = self.engine.execute_validated(decision, support_handler)

    @property
    def execution_key(self) -> str:
        return DurableStore.idempotency_key(
            "execute", self.decision.contract.mission_id, self.decision.global_report.action_id
        )

    @property
    def execution_status(self) -> str:
        return self.result.status


def executed_decision(path: Path, **kwargs) -> ExecutedDecision:
    """Build, attest and execute a decision against the database at `path`.

    The ledger reads the execution row from its own database, so the caller must
    pass the same path it will hand to OutcomeLedger.
    """
    return ExecutedDecision(build_decision(**kwargs), path)
