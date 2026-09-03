# SINGULAR — Empire Core

SINGULAR is a personal agentic operating system designed around one principle: maximize useful autonomy while minimizing unnecessary human effort, with fail-closed controls for sensitive actions.

## Architecture

- Commander / manager orchestration
- Specialist workforce
- World Model and persistent memory
- Mission Autopilot
- Execution Bus + Governor
- Human Task Filter + approval queue
- Event Bus and continuous supervisor loop
- Red Team / adversarial review
- Learning and evaluation
- System Architect / controlled evolution
- Audit trail and observability

## V1.6 additions

- `singular.empire`: event bus, agent registry, supervisor, mission runs, human-load metric
- `singular.v16_workforce`: default specialist workforce and capability planner
- `tests/test_v16.py`: workforce and supervisor tests

### Human-system specialists

The workforce explicitly includes two complementary specialists without creating a new hierarchy:

- `MENTAL`: functional mental state, cognitive load, recovery, self-regulation and sustainable performance. It may adapt workload and plans from observed state, but does not diagnose or replace professional care.
- `PRESENCE`: physical capacity, posture, presentation, voice, communication and social presence. It develops durable physical and interpersonal capability rather than optimizing appearance alone.

These specialists are advisory inputs to the existing Commander and World Model. They do not bypass governance or gain autonomous authority merely because their domain concerns the user directly.

## Safety model

Autonomy is permissioned, not assumed. Sensitive, high-risk, irreversible or explicitly human-required operations remain blocked/escalated unless an explicit authorization path exists.

## Next industrialization step

Connect real tools through MCP/function tools and the OpenAI Agents SDK; add durable external storage, real connectors, tracing/evals, scheduled event ingestion, and production deployment. The SDK supports agents, agent-as-tools/handoffs, guardrails, function tools, MCP, sessions, human-in-the-loop and tracing.

## V2 Empire Engine

- `singular.v2_empire`: capital snapshot, opportunity ranking, revenue experiments, strategic assets and empire snapshot.
- Economic layer is decision-support only: it never moves money, signs contracts, or bypasses the Governor.
- `tests/test_v2_empire.py`: 5 tests for runway, opportunity classification, risk blocking, revenue experiments, and strategic asset value.

## V2.1 — Empire Control

Adds the portfolio-control layer that decides where scarce resources should go before any real-world execution:
- `v2_1_control.py`: portfolio ranking/allocation, resource budgets, compounding-loop detection, risk concentration and unified empire snapshot.
- Explicit decisions: `FUND`, `TEST`, `HOLD`, `EXIT`.
- No external side effects: allocation is planning only and remains behind the Governor for real execution.

Control chain:
`WORLD MODEL → COMMANDER → WORKFORCE → PORTFOLIO → COMPOUNDING → RISK CONTROL → GOVERNOR → EXECUTION → MEASURE → LEARN`

Design principle: build an empire by compounding capabilities, capital, network, reputation and optionality—not by maximizing activity.

## V3 — Autonomous OS prototype

V3 closes the operating loop: signals → world model → deterministic decision → governed action routing → learning → controlled system-change proposals.

## V3.1 — Production Foundation

V3.1 makes the repository GitHub-ready without pretending it is already a deployed production service:

- `pyproject.toml` for reproducible packaging and optional runtime/dev dependencies.
- CI on Python 3.11–3.13 with lint, type checking and tests.
- environment configuration with `.env.example`; secrets are excluded from Git.
- structured safety boundary in `singular.security` (defense-in-depth).
- append-only in-memory audit trail in `singular.audit` (replaceable by durable storage later).
- health/readiness checks in `singular.health`.
- isolated optional OpenAI Agents SDK boundary in `singular.production_runtime`.
- autonomy policy and architecture documentation in `docs/`.

### Install

Core:

```bash
python -m pip install -e .
```

Development:

```bash
python -m pip install -e '.[dev]'
pytest -q
```

Optional Agents SDK runtime:

```bash
python -m pip install -e '.[runtime]'
```

V3.1 is a **production foundation**, not a claim that external integrations, durable persistence, deployment, monitoring, and real-world tool execution are complete. Those belong to the next integration phase.

## V3.2 — Governed Agent Core

V3.2 adds a controlled multi-specialist workforce layer with explicit routing, a deterministic Red Team gate, and defense-in-depth governance before any action reaches the execution bus.

Core rule: **no specialist can bypass the Governor, and no system change can silently modify SINGULAR.**

The workforce includes Strategy, Intelligence, Finance, Career, Business, Capability, Life, Mental and Presence specialists, plus Red Team and System Architect. Routing is selective rather than running every specialist on every task.

## V3.3 — Durable Mission Runtime

V3.3 adds a persistence boundary for mission contracts, human approvals, audit events and idempotency keys using SQLite. The durable runtime is intentionally infrastructure-light and restart-safe for the prototype phase; a managed database can replace it later without changing the governance domain model.

### Governance invariant

- GREEN: low-risk and sufficiently reversible actions may execute when the delegation contract permits it.
- ORANGE: preparation may proceed, but execution is escalated to human approval.
- RED: high-risk or poorly reversible actions are blocked fail-closed.
- BLACK: sensitive/forbidden actions are blocked fail-closed.

No approval is treated as execution. A human approval only clears the governance gate; the eventual external tool must still enforce its own execution contract and produce an auditable result.
