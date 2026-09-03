# Changelog

## 3.5.0 — Fail-Closed Validated Execution Boundary

- Added an immutable, tamper-evident `ValidatedTrajectoryDecision` as the sole executable authorization artifact.
- Bound validated execution to the exact handler target, or for external effects to provider implementation, provider name, operation and payload fingerprint.
- Disabled raw durable action, effect and reconciliation entry points; callers must present a validated decision.
- Closed direct execution bypasses in ToolFabric, MissionAutopilot and Empire AutopilotSupervisor.
- Added a mandatory construction pipeline: domain state -> Human Optimization -> exact Trajectory Optimization -> Trajectory Engine -> Global Decision Gate -> validated decision.
- Persisted the source domain/intervention/interaction inputs and re-ran deterministic human and trajectory optimization during validation to resist forged portfolios.
- Added strict `ActionRequest` validation for finite, bounded security-relevant numeric inputs and nonblank identifiers.
- Added adversarial tests for handler, provider, operation and payload substitution plus direct execution bypasses.
- Added durable `DecisionAttestationStore` issuance/revocation with TTL and exact context binding.
- Made the durable executor itself require a valid attestation, so the inner execution API cannot bypass the attestation registry.
- Bound durable execution identity fingerprints to the exact validated decision context fingerprint, preventing a different decision from silently reusing a completed execution identity.
- Added a strict execution adapter for external-effect execution and reconciliation, keeping both paths behind the same validated authority.
- Added a static/dynamic execution-boundary auditor that continuously checks for obvious production bypasses and raw API violations.
- Added evidence-bounded historical memory and probabilistic future reasoning: canonical facts, contested evidence, explicit mechanisms, long-horizon uncertainty and non-authorizing future scenarios.
- Added `TemporalAdvisor` to turn future scenarios into auditable PREPARE/WATCH forecast signals without granting authority.
- Kept the new execution boundary fail-closed until all production callers are migrated and CI is green.

## 3.4.3 — Interaction-Aware Trajectory Optimization

- Added a dedicated trajectory layer that evaluates portfolios rather than only individual interventions.
- Added explicit pairwise synergy and conflict effects with confidence discounting.
- Added exact deterministic portfolio evaluation for up to 22 candidates.
- Added fail-closed rejection beyond the exact search safety limit instead of silently presenting an approximation as optimal.
- Added regression coverage proving synergy can overturn individual rankings and conflicts can invalidate an otherwise attractive combination.
- Kept trajectory optimization recommendation-only; it cannot authorize execution or mutate governance.

## 3.4.2 — Decision Audit Hardening

- Replaced the large-search-space greedy fallback with deterministic branch-and-bound using an admissible optimistic bound and an explicit node budget.
- Preserved an explicit heuristic fallback only when the branch-and-bound budget is exhausted, with `exact=False` surfaced as a warning condition.
- Added duplicate cross-domain interaction rejection so the same causal edge cannot be silently double-counted.
- Made missing domain state auditable through explicit warnings instead of silently dropping interventions.
- Stopped the `DomainHypothesis` bridge from equating evidence strength with causal confidence; callers can now provide causal confidence explicitly.
- Added regression coverage for duplicate interactions, missing-state auditability and conservative causal bridging.

## 3.4.1 — Optimization Quality Hardening

- Replaced greedy small-portfolio selection with deterministic exact portfolio optimization for search spaces up to 22 candidates.
- Added deterministic tie-breaking for reproducible decisions.
- Added an explicit large-search-space heuristic fallback warning rather than presenting a heuristic as globally optimal.
- Preserved capacity, domain-diversification and governance constraints during portfolio selection.
- Added regression coverage proving the optimizer avoids a classic greedy-knapsack failure.

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
