from dataclasses import replace

import pytest

from singular.decision_attestation import ValidatedDecisionIssuer
from singular.durable import DurableStore
from singular.execution import DurableExecutionEngine
from singular.mission_runtime import DurableMissionRuntime
from singular.validated_pipeline import ValidatedTrajectoryPipeline
from test_validated_pipeline import AUTHORIZED_HANDLER_CAPABILITY, _inputs, authorized_handler


def build_decision(decision_id, dimensions=None, action_id=None):
    contract, action, state, intervention, profile, default_dimensions = _inputs()
    if action_id is not None:
        action = replace(action, id=action_id)
    chosen_dimensions = dimensions or default_dimensions
    return ValidatedTrajectoryPipeline.build(
        objective=contract.objective,
        actions=(action,),
        action_to_intervention=((action.id, intervention.id),),
        domain_states=(state,),
        interventions=(intervention,),
        trajectory_profile=profile,
        trajectory_dimensions=chosen_dimensions,
        contract=contract,
        execution_target=AUTHORIZED_HANDLER_CAPABILITY,
        decision_id=decision_id,
        capacity_budget=2,
    )


def test_execution_identity_is_bound_to_decision_context(tmp_path):
    first = build_decision("DEC-CONTEXT-1")
    altered_dimensions = {name: 0.8 for name in first.trajectory_profile.weights}
    altered_dimensions["learning"] = 0.9
    second = build_decision("DEC-CONTEXT-2", altered_dimensions, action_id=first.authorized_actions[0].id)
    assert first.context_fingerprint != second.context_fingerprint

    db = tmp_path / "singular.db"
    runtime = DurableMissionRuntime(DurableStore(db))
    runtime.store.save_mission(first.contract)
    executor = DurableExecutionEngine(runtime)
    issuer = ValidatedDecisionIssuer(executor.attestation_store)
    issuer.issue(first)
    issuer.issue(second)

    executor.execute_validated(first, authorized_handler)
    with pytest.raises(PermissionError, match="autorité, une décision ou un contenu différent"):
        executor.execute_validated(second, authorized_handler)


def test_execution_identity_binds_distinct_decision_id_even_with_same_context(tmp_path):
    first = build_decision("DEC-ID-1")
    second = build_decision("DEC-ID-2")
    assert first.context_fingerprint != second.context_fingerprint

    db = tmp_path / "singular.db"
    runtime = DurableMissionRuntime(DurableStore(db))
    runtime.store.save_mission(first.contract)
    executor = DurableExecutionEngine(runtime)
    issuer = ValidatedDecisionIssuer(executor.attestation_store)
    issuer.issue(first)
    issuer.issue(second)

    executor.execute_validated(first, authorized_handler)
    with pytest.raises(PermissionError, match="autorité, une décision ou un contenu différent"):
        executor.execute_validated(second, authorized_handler)


def test_attestation_and_execution_identity_survive_executor_restart(tmp_path):
    decision = build_decision("DEC-RESTART")
    db = tmp_path / "singular.db"

    runtime1 = DurableMissionRuntime(DurableStore(db))
    runtime1.store.save_mission(decision.contract)
    executor1 = DurableExecutionEngine(runtime1)
    ValidatedDecisionIssuer(executor1.attestation_store).issue(decision)
    first = executor1.execute_validated(decision, authorized_handler)
    assert first.status == "COMPLETED"

    runtime2 = DurableMissionRuntime(DurableStore(db))
    executor2 = DurableExecutionEngine(runtime2)
    assert executor2.attestation_store.verify(decision)
    second = executor2.execute_validated(decision, authorized_handler)
    assert second.status == "COMPLETED"
