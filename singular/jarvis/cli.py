"""Small command-line front door for the governed JARVIS runtime.

The CLI can propose and route work, but deliberately has no execute command.
Execution remains available only through SINGULAR's validated decision boundary.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from ..mission_runtime import DurableMissionRuntime
from ..durable import DurableStore
from .llm import AnthropicProvider, LLMProvider
from .runtime import JarvisRuntime


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="singular-jarvis", description="JARVIS proposal front door")
    parser.add_argument("request", help="human request to analyse")
    parser.add_argument("--context", default="", help="bounded context supplied to the model")
    parser.add_argument("--db", type=Path, default=Path("data/singular.db"), help="SINGULAR durable database")
    parser.add_argument("--model", default=None, help="Anthropic model override")
    parser.add_argument("--max-tokens", type=int, default=JarvisRuntime.DEFAULT_MAX_TOKENS)
    parser.add_argument("--route", action="store_true", help="also create the governed mission and decisions")
    return parser


def _proposal_dict(proposal) -> dict[str, object]:
    return {
        "objective": proposal.objective,
        "expected_result": proposal.expected_result,
        "context_needed": list(proposal.context_needed),
        "actions": [
            {
                "name": action.name,
                "description": action.description,
                "impact": action.impact,
                "risk": action.risk,
                "reversibility": action.reversibility,
                "priority": proposal.priorities[index].score,
                "priority_reasons": list(proposal.priorities[index].reasons),
                "requires_human": action.requires_human,
                "sensitive": action.sensitive,
            }
            for index, action in enumerate(proposal.actions)
        ],
        "llm": {
            "model": proposal.llm.model,
            "input_tokens": proposal.llm.usage.input_tokens,
            "output_tokens": proposal.llm.usage.output_tokens,
        },
    }


def run(
    request: str,
    *,
    context: str = "",
    provider: LLMProvider | None = None,
    mission_runtime: DurableMissionRuntime | None = None,
    max_tokens: int = JarvisRuntime.DEFAULT_MAX_TOKENS,
    model: str | None = None,
    route: bool = False,
) -> dict[str, object]:
    """Run JARVIS proposal/route without exposing an execution primitive."""
    selected_provider = provider or AnthropicProvider(model=model)
    runtime = JarvisRuntime(
        selected_provider,
        mission_runtime=mission_runtime or DurableMissionRuntime(DurableStore("data/singular.db")),
        max_tokens=max_tokens,
    )
    proposal = runtime.propose(request, context=context)
    output = _proposal_dict(proposal)
    if not route:
        return output
    contract, decisions = runtime.route(proposal)
    output["mission"] = {
        "mission_id": contract.mission_id,
        "objective": contract.objective,
        "decisions": [
            {
                "action_id": decision.action.id,
                "governor_mode": decision.governor.mode.value,
                "can_prepare": decision.can_prepare,
                "can_execute": decision.can_execute,
                "requires_human": decision.requires_human,
            }
            for decision in decisions
        ],
    }
    return output


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run(
            args.request,
            context=args.context,
            max_tokens=args.max_tokens,
            model=args.model,
            route=args.route,
            mission_runtime=DurableMissionRuntime(DurableStore(args.db)),
        )
    except Exception as exc:
        print(json.dumps({"error": "JARVIS request failed", "type": type(exc).__name__}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
