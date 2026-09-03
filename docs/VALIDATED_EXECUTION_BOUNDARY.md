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
    -> DurableExecutionEngine
    -> handler/provider
```

Every executable path must preserve the complete context needed to reproduce the authorization decision.

## Validated artifact invariants

A `ValidatedTrajectoryDecision` is executable only when all of the following hold:

- global decision is `PROCEED`;
- trajectory assessment is `PROCEED` and does not require human review;
- Human Optimization and Trajectory Optimization inputs/results reproduce exactly;
- selected portfolio candidates originate from Human Optimization and are executable proposals;
- the authorized action belongs to the selected portfolio and is bound to the mission contract;
- policy, Governor and Red Team findings are recomputed and identical to the stored authorization;
- all security-relevant numeric values are finite and bounded;
- the complete artifact is covered by a deterministic SHA-256 fingerprint.

## Execution-target binding

For a normal handler, the artifact stores the handler's module/qualified-name target and the executor verifies the supplied callable against it before invoking the handler.

For an external effect, the artifact stores:

- provider implementation target;
- provider name;
- operation;
- canonical SHA-256 fingerprint of the exact payload.

The executor rechecks all four values before the provider is reached. A provider, operation, or payload substitution is therefore rejected before runtime authorization or external side effects.

## Raw paths

These public methods are intentionally deny-by-default:

- `DurableExecutionEngine.execute`
- `DurableExecutionEngine.execute_effect`
- `DurableExecutionEngine.reconcile_effect`
- `ToolFabric.execute_autonomous`
- `ToolFabric.execute_approved`
- `MissionAutopilot.run` handler execution
- `AutopilotSupervisor.route` handler execution

Callers must migrate to the validated boundary instead of restoring compatibility through raw execution.

## Replay and TOCTOU resistance

The durable executor re-evaluates current governance and policy immediately before execution and compares them with the validated artifact. Durable execution identities are idempotent and fingerprinted. A previously authorized action cannot silently acquire new parameters, contract context, policy, or governance and still execute under the old identity.

## Human review

Sensitive actions and actions requiring human judgment remain non-executable through this artifact. `ValidatedTrajectoryDecision` accepts only executable Governor modes and rejects pending human review.

## Integration rule

`GlobalDecisionGate` remains usable for advisory recommendations. That is not an execution authorization. Only `ValidatedTrajectoryDecision` can cross the durable execution boundary.

Do not merge this architecture into `main` until the branch CI is green and all production callers have migrated to the validated path.
