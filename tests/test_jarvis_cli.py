from __future__ import annotations

import json
from pathlib import Path

from singular.durable import DurableStore
from singular.jarvis.cli import main, run
from singular.jarvis.llm import LLMResponse, LLMUsage
from singular.mission_runtime import DurableMissionRuntime


class FakeProvider:
    def complete(self, *, system: str, user: str, max_tokens: int) -> LLMResponse:
        assert "SINGULAR est l'autorité" in system
        assert max_tokens == 321
        assert "REQUEST:\nInspect the repository" in user
        return LLMResponse(
            text=json.dumps(
                {
                    "objective": "Inspect the repository",
                    "expected_result": "A bounded inspection plan",
                    "context_needed": [],
                    "actions": [
                        {
                            "name": "inspect",
                            "description": "Inspect repository state",
                            "impact": 2,
                            "risk": 0,
                            "reversibility": 10,
                            "leverage": 8,
                            "dependency": 8,
                            "uncertainty": 2,
                            "cost": 1,
                            "learning": 8,
                            "ownership": 1,
                            "recurrence": 1,
                            "requires_human": False,
                            "sensitive": False,
                            "capability": "cap_model_must_not_authorize",
                        }
                    ],
                }
            ),
            usage=LLMUsage(input_tokens=12, output_tokens=34),
            model="fake",
        )


def test_cli_run_returns_proposal_without_execution(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))
    result = run(
        "Inspect the repository",
        provider=FakeProvider(),
        mission_runtime=runtime,
        max_tokens=321,
    )

    assert result["objective"] == "Inspect the repository"
    assert result["actions"][0]["name"] == "inspect"
    assert result["actions"][0]["priority"] > 0
    assert "mission" not in result
    assert runtime.store.audit_events() == ()


def test_cli_route_creates_governed_plan_but_no_execution(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))
    result = run(
        "Inspect the repository",
        provider=FakeProvider(),
        mission_runtime=runtime,
        max_tokens=321,
        route=True,
    )

    mission = result["mission"]
    assert mission["mission_id"]
    assert mission["decisions"][0]["can_prepare"] is True
    execution_key = runtime.store.idempotency_key(
        "execute", mission["mission_id"], mission["decisions"][0]["action_id"]
    )
    assert runtime.store.get_execution(execution_key) is None


def test_cli_main_emits_json_and_nonzero_on_missing_anthropic_key(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main(["Inspect the repository", "--db", str(tmp_path / "singular.db")]) == 1
    stderr = capsys.readouterr().err
    payload = json.loads(stderr.strip().splitlines()[-1])
    assert payload["error"] == "JARVIS request failed"
