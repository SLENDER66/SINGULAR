## 3.2.0
- Added governed specialist workforce routing.
- Added deterministic Red Team pre-execution gate.
- Added defense-in-depth governed executor.
- Added 4 governance/workforce tests.
- Total test suite: 47 passing.

# Changelog

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

## 3.3.0
- Added durable SQLite persistence for missions, approvals and audit events.
- Added deterministic idempotency-key primitive.
- Added restart-safe `DurableMissionRuntime`.
- Strengthened ORANGE governance: preparation is allowed, execution requires human approval.
- Kept RED/BLACK fail-closed behavior.
- Added persistence and adversarial governance tests.
