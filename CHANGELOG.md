# Changelog

## 3.4.0 — Canonical Human Optimization

- Consolidated the two Human Optimization implementations around `singular.human_optimization`.
- Preserved the historical `singular.human_optimizer` API as a compatibility facade with no independent optimization math.
- Added target-aware domain state, dependency-aware bottleneck detection and cross-domain interaction strength.
- Added intervention dimensions for causal confidence, capacity, reversibility, time-to-result, recurrence and cross-domain impact.
- Added explicit expected global gain, capacity accounting and uncertainty reporting.
- Added a bridge from `DomainHypothesis` to the canonical intervention model.
- Integrated Human Optimization into `GlobalDecisionGate` as advisory decision context; it cannot authorize execution.
- Added regression, edge-case, capacity, uncertainty and global-control integration tests.

## 3.3.0
- Added durable SQLite persistence for missions, approvals and audit events.
- Added deterministic idempotency-key primitive.
- Added restart-safe `DurableMissionRuntime`.
- Strengthened ORANGE governance: preparation is allowed, execution requires human approval.
- Kept RED/BLACK fail-closed behavior.
- Added persistence and adversarial governance tests.

## 3.2.0
- Added governed specialist workforce routing.
- Added deterministic Red Team pre-execution gate.
- Added defense-in-depth governed executor.
- Added 4 governance/workforce tests.

## 3.1.0 — Production Foundation

- Added typed environment configuration and safe defaults.
- Added defense-in-depth action policy for autonomy boundaries.
- Added append-only in-memory audit trail.
- Added health/readiness checks.
- Isolated the optional OpenAI Agents SDK runtime boundary.
- Added GitHub Actions CI for Python 3.11–3.13.
- Added Ruff and mypy development configuration.
- Fixed V3 action preparation so an explicitly supplied delegation contract is actually routed to the Governor.
- Added security, autonomy and architecture documentation.
