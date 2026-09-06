# Changelog

## 3.6.0 — Artifact Identity, Bounded Integrity, and the Sage

Security — artifact identity:

- `artifact_fingerprint` now covers the whole code object (constants recursing into nested code, global and attribute names, varnames, freevars, cellvars, argument counts, flags) plus a function's defaults and keyword defaults. It hashed `co_code` alone, so two same-named implementations differing only in which URL they post to were one artifact — the substitution the durable capability record exists to refuse.
- A class's non-`__code__` attributes now count too: properties through their getter/setter/deleter, `functools.partial` through its target and bound arguments, callable instances through their `__call__`, and constants by value. Mutable class attributes are recorded by type only, so a cache cannot revoke a live capability.
- Execution capability schema is v2. A v1 row's fingerprint cannot be recomputed and cannot be trusted, so opening a v1 database revokes every binding with a reason naming the rotation.
- `ExecutionCapabilityRegistry.attach()` attaches the durable store before writing bindings, so a partial failure leaves the registry stricter rather than reverting to in-memory verification, and refuses to replace an already-attached store. `revoke()` writes durably first, so a failed write can no longer leave a token dead in this process and ACTIVE in the next.
- `improvement_registry.artifact_fingerprint` no longer falls back to `str()`: data is canonicalised by value and type, code by the boundary's code identity, and an object that can state neither is refused rather than fingerprinted by its memory address. Schema is v3.

Integrity and recovery:

- The durable integrity scan reads every table in one deferred read transaction. Executions and mission statuses were read at different instants, so a concurrent writer could show the scan a contradiction that never existed — and the boundary refuses every execution while the scan is dirty.
- The execution gate scans the mission being executed rather than the whole database. One bad row anywhere used to shut every mission permanently, with no supported repair. `check()` with no argument remains the operator's whole-database view.
- `executions(mission_id)` and `external_effects(execution_key)` are indexed.

Journal:

- A decision recorded with an integer cost broke the hash chain from its first entry, permanently: the value was fingerprinted as written and read back as a float. Values are canonicalised before fingerprinting.

The Sage:

- Added `singular/sage/`: an observation engine that turns the journal into a daily report, and a standard-library web app installable on a phone's home screen. It is advisory by construction — a test refuses any import of the execution boundary from the package.
- Added `ios/SingularSage/`: the same engine as a native SwiftUI iPhone app, pinned to the Python implementation by generated vectors that assert identical output text.

## 3.5.2 — Governed Control Plane & Continuous Improvement

- Added `SingularControlPlane` as the canonical top-level lifecycle surface for build -> attest -> execute -> observe outcome.
- Added `ControlPlaneDecision` so a validated decision and its durable attestation travel together at the orchestration layer.
- Added a durable outcome ledger binding forecast, actual result, execution status and exact decision context fingerprint.
- Added a human-reviewed learning queue and bounded self-improvement engine; observed error can create a test proposal, never silent policy mutation.
- Added `TemporalAdvisor` forecast signals with explicit non-authorizing semantics.
- Hardened `DecisionAttestationStore` so `:memory:` instances remain valid across internal SQLite connections.
- Expanded execution-boundary static auditing to detect aliases of the durable executor and direct calls to its inner validated methods outside the canonical adapter/service.
- Added regression coverage for the top-level control plane and the learning lifecycle.

## 3.5.1 — Execution Boundary Hardening

- Made durable execution itself require a valid, active `DecisionAttestationStore` record; the inner executor can no longer bypass durable issuance/revocation checks.
- Bound durable execution identities to the exact `ValidatedTrajectoryDecision.context_fingerprint`, preventing a distinct decision context from reusing the same mission/action execution identity.
- Routed handler execution, external-effect execution and external-effect reconciliation through the strict validated boundary surface.
- Added a static/dynamic `ExecutionBoundaryAuditor` for production call-site bypass detection, direct inner-executor detection and deny-by-default raw API probes.
- Added a canonical `ValidatedDecisionService` lifecycle surface so production callers can build, attest, execute and revoke decisions without manually sequencing security-critical primitives.
- Added a durable outcome ledger that binds forecast, actual outcome, execution status and decision context for calibration and replay-safe learning.
- Added a human-reviewed learning proposal queue and a bounded self-improvement engine; measured error can produce strategy tests, but never automatic policy or authorization mutation.
- Strengthened historical reasoning so contested evidence remains counterevidence instead of inflating pattern support.
- Added explicit temporal forecast signals for collective cognition while preserving a non-authorizing boundary.
- Expanded adversarial tests for attestation, restart, replay identity, external-effect routing, temporal authority separation and continuous-learning governance.

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
- Added evidence-bounded historical memory and probabilistic future reasoning, with explicit canonical facts, contested evidence, assumptions, horizon uncertainty and non-authorizing future scenarios.
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
