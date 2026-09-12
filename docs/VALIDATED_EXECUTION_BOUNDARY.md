# Validated Execution Boundary

## Purpose

SINGULAR must never execute an external action merely because a caller possesses an `ActionRequest`, an approval, or a recommendation. Executable authority is represented by one immutable artifact: `ValidatedTrajectoryDecision`.

## Required construction order

```text
DomainLearning
    -> HumanOptimization
    -> TrajectoryOptimization
    -> TrajectoryEngine
    -> GlobalDecisionGate
    -> ValidatedTrajectoryDecision
    -> DurableDecisionAttestation
    -> ValidatedExecutionBoundary
    -> DurableExecutionEngine
    -> handler/provider
```

Every executable path must preserve the complete context needed to reproduce the authorization decision.

## Canonical production surface

Production callers should prefer `SingularControlPlane` rather than directly sequencing low-level primitives:

```text
control_plane.construct_and_attest(...)
          |
          +--> ValidatedTrajectoryPipeline
          +--> DecisionAttestationStore
          |
          v
   ControlPlaneDecision
          |
     +----+----+
     |         |
 execute    observe_outcome
     |         |
     v         v
 durable    OutcomeLedger
 execution       |
                 v
          LearningReviewQueue
                 |
                 v
        human-reviewed proposal
```

This facade is orchestration, not an extra authorization layer. The actual execution permission remains inside the validated decision plus durable attestation and the durable executor.

## Authority invariant

The system separates cognition from authority:

```text
evidence / analysis / forecast / recommendation
              |
              v
      decision recommendation
              |
              v
   GlobalDecisionGate (advisory)
              |
              v
 ValidatedTrajectoryDecision
              |
              v
 durable attestation
              |
              v
 validated execution boundary
              |
              v
     durable side effect
```

A recommendation is not an authorization. A global `PROCEED` report is not, by itself, an authorization. An approval record is not, by itself, an authorization. Future scenarios and collective consensus are never executable authority.

## Validated artifact invariants

A `ValidatedTrajectoryDecision` is executable only when all of the following hold:

- global decision is `PROCEED`;
- trajectory assessment is `PROCEED` and does not require human review;
- Human Optimization and Trajectory Optimization inputs/results reproduce exactly;
- selected portfolio candidates originate from Human Optimization and are executable proposals;
- the authorized action belongs to the selected portfolio and is bound to the mission contract;
- policy, Governor and Red Team findings are recomputed and identical to the stored authorization;
- all security-relevant numeric values are finite and bounded;
- the decision has a finite validity interval (`issued_at < now < expires_at`);
- the complete artifact, including its validity interval and execution binding, is covered by a deterministic SHA-256 fingerprint.

## Durable attestation

A decision must also be durably issued before it can execute. `DecisionAttestationStore` binds:

- decision id;
- complete decision context fingerprint;
- issuance and expiration timestamps;
- issuer;
- revocation state.

Attestation is idempotent for the exact same decision and refuses reuse of an existing decision id with another context. Revocation is durable and cannot be followed by re-issuance of the same decision id.

The durable executor performs this check itself. The outer `ValidatedExecutionBoundary` is defense in depth, not a substitute for the inner execution check.

## Execution-target binding

The textual module/qualified-name target is retained only as descriptive metadata. Executable authority is an opaque capability id (`cap_...`) registered against the exact in-process handler or provider object. The durable executor requires the supplied object to be the same registered object; copied callables and forged `__module__`/`__qualname__` metadata do not satisfy the binding.

For an external effect, the artifact additionally stores:

- provider implementation target metadata;
- provider name;
- operation;
- canonical SHA-256 fingerprint of the exact payload.

The executor rechecks the opaque capability, provider name, operation and payload fingerprint before the provider is reached. A provider, operation, or payload substitution is rejected before external side effects.

## Durable execution identity

The durable execution identity is bound to the exact `ValidatedTrajectoryDecision.context_fingerprint`. This closes a class of replay errors where the same mission/action pair could otherwise collide across different validated contexts.

The execution identity includes the mission, action security fields, current governance state, contract and decision context fingerprint. Completed or failed executions are replayed only when this identity still matches.

## Temporal validity and replay

Validated decisions are short-lived by default. The construction pipeline issues a bounded validity window and includes both timestamps in the artifact fingerprint. A decision is invalid before `issued_at` or at/after `expires_at`.

The durable executor re-evaluates current governance and policy immediately before execution. An attestation may be revoked independently of the decision's cryptographic self-consistency, which makes revocation an additional durable gate.

## Historical and future cognition

Historical memory is evidence-bounded. Established and probable facts may enter the canonical world snapshot; contested evidence remains explicitly visible as counterevidence. Historical patterns represent mechanisms rather than moral labels.

Future scenarios remain hypotheses with explicit assumptions, probability, evidence and horizon. Long horizons increase uncertainty. `TemporalAdvisor` can produce `PREPARE` or `WATCH` signals and can expose forecasts to collective cognition, but it is structurally non-authorizing.

```text
historical evidence -> mechanisms -> patterns
                              \
future scenarios ----> bounded temporal advisory
                              |
                              +--> cognition only
                                   never authority
```

## Collective cognition

Shared signals are typed as evidence, analysis, forecast, challenge or recommendation. Repeated contributions from one contributor do not create a majority. Critical challenges remain blocking. Consensus is explicitly separate from authorization.

Temporal forecasts enter this space as `FORECAST` signals with noncritical authority and therefore cannot silently turn a scenario into an action.

## Learning and self-improvement

SINGULAR now closes the operational loop without granting the learning system authority over itself:

```text
validated decision
      |
      v
executed outcome + forecast
      |
      v
OutcomeLedger
      |
      v
forecast calibration
      |
      v
LearningReviewQueue
      |
      v
LearningStrategyEngine
      |
      v
reviewable TEST / ADOPT / HOLD proposal
```

`OutcomeLedger` binds the result to the exact decision context fingerprint, making it possible to distinguish outcomes produced under materially different decisions. Its append-only chain is tamper-evident. `LearningReviewQueue` persists a human review state (`PENDING`, `ACCEPTED`, `REJECTED`). `SelfImprovementEngine` can construct a strategy proposal from measured error, but `mutation_authorized` is structurally false.

A learning result therefore follows this rule:

```text
measurement -> proposal -> human review -> future implementation
```

and never:

```text
measurement -> automatic policy mutation -> automatic new authority
```

The architecture deliberately separates learning from authorization so that improved predictive performance cannot silently expand SINGULAR's power.

## Raw paths

These public methods are intentionally deny-by-default:

- `DurableExecutionEngine.execute`
- `DurableExecutionEngine.execute_effect`
- `DurableExecutionEngine.reconcile_effect`
- `ToolFabric.execute_autonomous`
- `ToolFabric.execute_approved`
- `MissionAutopilot.run` handler execution
- `AutopilotSupervisor.route` handler execution

The strict boundary also exposes only validated variants for handler execution, external-effect execution and external-effect reconciliation.

## Self-audit

`ExecutionBoundaryAuditor` provides a static/dynamic integrity check that:

- scans production Python files for obvious raw-tool, raw-engine and direct-handler bypasses;
- detects common aliases of `DurableExecutionEngine`;
- detects direct use of inner validated executor methods outside the canonical adapter/service;
- parses every checked production file;
- probes the legacy raw methods and requires `PermissionError`.

This is a guardrail, not a formal proof. It is intentionally conservative and should be extended whenever a new execution surface appears.

## Human review

Sensitive actions and actions requiring human judgment remain non-executable through this artifact. `ValidatedTrajectoryDecision` accepts only executable Governor modes and rejects pending human review.

Learning proposals are likewise non-executable: accepting a learning review does not automatically rewrite policies, capabilities, Governor configuration or authorization rules.

## Integration rule

`GlobalDecisionGate` remains usable for advisory recommendations. That is not an execution authorization. Only an attested `ValidatedTrajectoryDecision` can cross the durable execution boundary.

This architecture is no longer isolated on a feature branch: CI is green, production callers are migrated, and the work lives on the default branch's lineage. `feat/validated-execution-boundary` is dead. Do not merge into `main` without explicit human authorization.
