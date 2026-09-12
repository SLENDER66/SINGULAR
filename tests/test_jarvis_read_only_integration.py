from __future__ import annotations

from pathlib import Path

from singular.autopilot import Autonomy
from singular.control_plane import SingularControlPlane
from singular.domain_learning import LearningDomain
from singular.durable import DurableStore
from singular.human_optimization import DomainState, Intervention
from singular.jarvis.llm import LLMResponse
from singular.jarvis.read_only import make_read_only_repository_tool, verify_read_only_result
from singular.jarvis.runtime import MissionProposal, ProposedAction
from singular.jarvis.validated_bridge import JarvisValidatedBridge
from singular.mission_runtime import DurableMissionRuntime
from singular.trajectory import TrajectoryProfile
from singular.values import Vision


def test_jarvis_read_only_crosses_validated_boundary_and_is_verified(tmp_path: Path):
    (tmp_path / "README.md").write_text("SINGULAR", encoding="utf-8")
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))
    control = SingularControlPlane(runtime)
    capability, handler = make_read_only_repository_tool(
        tmp_path,
        capability_id="cap_test_jarvis_read_only_e2e",
    )

    action = ProposedAction(
        name="read:README.md",
        description="Read one bounded repository file",
        impact=2,
        risk=0,
        reversibility=10,
        leverage=8,
        dependency=7,
        uncertainty=1,
        cost=1,
        learning=7,
        ownership=1,
        recurrence=1,
    )
    proposal = MissionProposal(
        objective="Inspect repository state",
        expected_result="Bounded repository content is returned",
        context_needed=(),
        actions=(action,),
        llm=LLMResponse(text="{}", model="test"),
    )
    state = DomainState(LearningDomain.CAREER, 0.2, confidence=0.9)
    intervention = Intervention(
        "repository_read",
        LearningDomain.CAREER,
        0.9,
        evidence=0.9,
        causal_confidence=0.9,
        capacity=1,
    )
    profile = TrajectoryProfile(
        Vision("Build a resilient long-term system"),
        money=1,
        time=1,
        capability=2,
        energy=1,
        freedom=1,
        ownership=1,
        learning=2,
        resilience=1,
        transmission=1,
    )
    dimensions = {name: 0.8 for name in profile.weights}

    bridge = JarvisValidatedBridge(runtime, control.decisions)
    decision, attestation = bridge.build_and_attest(
        proposal,
        execution_target=capability,
        intervention_id=intervention.id,
        domain_states=(state,),
        interventions=(intervention,),
        trajectory_profile=profile,
        trajectory_dimensions=dimensions,
        capacity_budget=2,
        decision_id="DEC-JARVIS-READ-E2E",
        mission_kwargs={"autonomy": Autonomy.EXECUTE_REVERSIBLE},
    )

    assert attestation.decision_id == decision.decision_id
    assert control.decisions.is_attested(decision)
    assert decision.verify()
    assert decision.contract.autonomy == Autonomy.EXECUTE_REVERSIBLE

    result = control.decisions.execute(decision, decision.authorized_actions[0].id, handler)

    assert result.status == "COMPLETED"
    assert result.result["path"] == "README.md"
    assert verify_read_only_result(tmp_path, decision.authorized_actions[0], result.result)

    audit_events = runtime.store.audit_events()
    assert any(event.get("event_type") == "governance_route" for event in audit_events)

    # A second execution with the same validated decision must be idempotent,
    # not a second filesystem effect.
    second = control.decisions.execute(decision, decision.authorized_actions[0].id, handler)
    assert second.execution_key == result.execution_key
