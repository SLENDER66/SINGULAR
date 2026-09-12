from __future__ import annotations

from dataclasses import dataclass

import pytest

from singular.jarvis import LLMResponse, LLMUsage, MissionProposal, ProposedAction
from singular.jarvis.validated_bridge import JarvisValidatedBridge
from singular.mission_runtime import DurableMissionRuntime


@dataclass
class FakeDecisionService:
    calls: list[dict]

    def build_and_attest(self, **kwargs):
        self.calls.append(kwargs)
        return "DECISION", "ATTESTATION"


def proposal() -> MissionProposal:
    return MissionProposal(
        objective="Inspecter le dépôt",
        expected_result="Un résultat vérifiable",
        context_needed=(),
        actions=(
            ProposedAction(
                name="inspect",
                description="Inspection read-only",
                impact=4,
                risk=1,
                reversibility=10,
            ),
        ),
        llm=LLMResponse("{}", LLMUsage(1, 1), "fake"),
    )


def test_bridge_delegates_to_existing_validated_service(tmp_path):
    service = FakeDecisionService([])
    bridge = JarvisValidatedBridge(DurableMissionRuntime(), service)

    result = bridge.build_and_attest(
        proposal(),
        execution_target="cap_read_only",
        intervention_id="inspect",
        domain_states=(),
        interventions=(),
        trajectory_profile=object(),
        trajectory_dimensions={},
        capacity_budget=0,
        decision_id="DEC-JARVIS-1",
    )

    assert result == ("DECISION", "ATTESTATION")
    call = service.calls[0]
    assert call["execution_target"] == "cap_read_only"
    assert call["action_to_intervention"][0][1] == "inspect"
    assert call["actions"][0].execution_capability == "cap_read_only"
    assert call["actions"][0].name == "inspect"


def test_bridge_rejects_non_opaque_execution_target():
    bridge = JarvisValidatedBridge(DurableMissionRuntime(), FakeDecisionService([]))
    with pytest.raises(ValueError, match="opaque capability"):
        bridge.build_and_attest(
            proposal(),
            execution_target="read_file",
            intervention_id="inspect",
            domain_states=(),
            interventions=(),
            trajectory_profile=object(),
            trajectory_dimensions={},
            capacity_budget=0,
            decision_id="DEC-JARVIS-2",
        )


def test_bridge_rejects_invalid_action_index():
    bridge = JarvisValidatedBridge(DurableMissionRuntime(), FakeDecisionService([]))
    with pytest.raises(IndexError):
        bridge.build_and_attest(
            proposal(),
            execution_target="cap_read_only",
            intervention_id="inspect",
            domain_states=(),
            interventions=(),
            trajectory_profile=object(),
            trajectory_dimensions={},
            capacity_budget=0,
            decision_id="DEC-JARVIS-3",
            action_index=1,
        )
