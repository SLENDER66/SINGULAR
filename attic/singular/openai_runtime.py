from __future__ import annotations


class OpenAIRuntimeUnavailable(RuntimeError):
    pass


def build_runtime(model: str = "gpt-5"):
    """Optional OpenAI Agents SDK adapter kept outside deterministic policy logic."""
    try:
        from agents import Agent, Runner
    except ImportError as exc:
        raise OpenAIRuntimeUnavailable(
            "Install the current openai-agents package to enable the LLM runtime."
        ) from exc

    commander = Agent(
        name="SINGULAR_COMMANDER",
        model=model,
        instructions=(
            "You are SINGULAR's Commander. Orchestrate specialist reasoning, "
            "preserve uncertainty, propose actions, and never bypass the external policy/governor layer."
        ),
    )
    return Runner, commander
