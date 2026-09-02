# SINGULAR Architecture

`WORLD MODEL → COMMANDER → WORKFORCE → PORTFOLIO → RED TEAM → GOVERNOR → EXECUTION → RESULT → LEARNING → SYSTEM ARCHITECT`

The domain core is deterministic and can run without an LLM. The OpenAI Agents SDK is isolated behind `singular.production_runtime` so model/runtime dependencies do not contaminate the core domain layer.

System evolution is proposal-based: the System Architect may recommend changes, but it cannot silently modify production behavior.
