from __future__ import annotations

import json

import pytest

from singular.jarvis import AnthropicProvider, JarvisRuntime, LLMResponse, LLMUsage
from singular.jarvis.llm import LLMProviderError


class FakeProvider:
    def __init__(self, text: str):
        self.text = text
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return LLMResponse(self.text, LLMUsage(11, 7), "fake")


def proposal_text(**overrides):
    data = {
        "objective": "Réduire le temps de traitement",
        "expected_result": "Un plan vérifiable",
        "context_needed": ["délai actuel"],
        "actions": [
            {
                "name": "inspect",
                "description": "Inspecter les données disponibles",
                "impact": 6,
                "risk": 1,
                "reversibility": 10,
                "requires_human": False,
                "sensitive": False,
                "capability": "repo.read",
            }
        ],
    }
    data.update(overrides)
    return json.dumps(data)


def test_provider_response_becomes_bounded_proposal():
    provider = FakeProvider(proposal_text())
    runtime = JarvisRuntime(provider)

    proposal = runtime.propose("Analyse mon dépôt")

    assert proposal.objective == "Réduire le temps de traitement"
    assert proposal.actions[0].impact == 6.0
    assert proposal.actions[0].risk == 1.0
    assert provider.calls[0]["max_tokens"] == 1200


def test_trajectory_priority_is_deterministic_and_test_first():
    provider = FakeProvider(proposal_text(actions=[
        {
            "name": "experiment",
            "description": "Tester une hypothèse à faible coût",
            "impact": 7,
            "risk": 1,
            "reversibility": 10,
            "leverage": 9,
            "dependency": 8,
            "uncertainty": 9,
            "cost": 2,
            "learning": 10,
            "ownership": 8,
            "recurrence": 7,
            "requires_human": False,
            "sensitive": False,
            "capability": "repo.read",
        }
    ]))
    runtime = JarvisRuntime(provider)

    priorities = runtime.propose("Teste l'hypothèse").priorities

    assert priorities[0].test_first is True
    assert "LOW_COST_TEST_FIRST" in priorities[0].reasons
    assert priorities[0].score > 0


def test_route_orders_actions_by_deterministic_trajectory_priority():
    provider = FakeProvider(proposal_text(actions=[
        {
            "name": "risky",
            "description": "Action locale mais coûteuse",
            "impact": 8,
            "risk": 8,
            "reversibility": 2,
            "leverage": 2,
            "dependency": 2,
            "uncertainty": 2,
            "cost": 9,
            "learning": 1,
            "ownership": 0,
            "recurrence": 0,
            "requires_human": False,
            "sensitive": False,
            "capability": "repo.read",
        },
        {
            "name": "safe",
            "description": "Expérience réversible et utile",
            "impact": 6,
            "risk": 1,
            "reversibility": 10,
            "leverage": 9,
            "dependency": 8,
            "uncertainty": 8,
            "cost": 2,
            "learning": 9,
            "ownership": 7,
            "recurrence": 6,
            "requires_human": False,
            "sensitive": False,
            "capability": "repo.read",
        },
    ]))
    runtime = JarvisRuntime(provider)

    _, decisions = runtime.route(runtime.propose("Priorise la meilleure trajectoire"))

    assert [decision.action.name for decision in decisions] == ["safe", "risky"]
    assert all(decision.action.contract_id is not None for decision in decisions)


def test_route_never_executes_provider_and_governor_stays_in_control():
    provider = FakeProvider(proposal_text())
    runtime = JarvisRuntime(provider)

    contract, decisions = runtime.route(runtime.propose("Inspecte le dépôt"))

    assert contract.mission_id.startswith("MIS-")
    assert len(decisions) == 1
    assert decisions[0].can_prepare is True
    assert decisions[0].can_execute is False


def test_malformed_model_output_fails_closed():
    provider = FakeProvider('{"objective":"x","expected_result":"y","actions":[{')
    runtime = JarvisRuntime(provider)

    with pytest.raises(ValueError):
        runtime.propose("Fais quelque chose")


def test_invalid_numeric_input_is_rejected():
    provider = FakeProvider(proposal_text(actions=[{
        "name": "x",
        "description": "x",
        "impact": float("nan"),
        "risk": 1,
        "reversibility": 10,
        "requires_human": False,
        "sensitive": False,
        "capability": None,
    }]))
    runtime = JarvisRuntime(provider)

    with pytest.raises(ValueError):
        runtime.propose("Fais quelque chose")


def test_anthropic_adapter_sanitizes_provider_failure():
    class BrokenClient:
        class Messages:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("Authorization: Bearer SUPER_SECRET")

        messages = Messages()

    provider = AnthropicProvider(api_key="not-used-by-injected-client", client=BrokenClient())
    with pytest.raises(LLMProviderError, match="Anthropic request failed") as exc:
        provider.complete(system="system", user="user", max_tokens=10)
    assert "SUPER_SECRET" not in str(exc.value)
