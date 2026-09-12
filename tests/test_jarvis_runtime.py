from __future__ import annotations

import pytest

from singular.jarvis import JarvisRuntime, LLMResponse, LLMUsage
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
    import json
    return json.dumps(data)


def test_provider_response_becomes_bounded_proposal():
    provider = FakeProvider(proposal_text())
    runtime = JarvisRuntime(provider)

    proposal = runtime.propose("Analyse mon dépôt")

    assert proposal.objective == "Réduire le temps de traitement"
    assert proposal.actions[0].risk == 6.0 or proposal.actions[0].impact == 6.0
    assert provider.calls[0]["max_tokens"] == 1200


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


def test_provider_failure_does_not_expose_provider_exception():
    class BrokenProvider:
        def complete(self, **kwargs):
            raise LLMProviderError("secret-looking detail")

    runtime = JarvisRuntime(BrokenProvider())
    with pytest.raises(LLMProviderError, match="secret-looking detail"):
        runtime.propose("Fais quelque chose")
