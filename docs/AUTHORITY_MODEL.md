# SINGULAR — Authoritative Execution Model

## Purpose

SINGULAR must have one authoritative reality for whether an action executed, failed, or remains unresolved. Derived projections, process-local objects, learning records, and provider responses are not execution authority.

## Authority hierarchy

1. **ValidatedTrajectoryDecision** — authorization input. It does not itself prove execution.
2. **`executions` durable row** — authoritative lifecycle of the SINGULAR execution.
3. **`external_effects` durable row** — authoritative evidence of the corresponding external side effect.
4. **Atomic durable finalization** — the only operation that converts durable external proof into a terminal SINGULAR execution and mission state.
5. **Outcome/learning projections** — consumers of verified terminal execution evidence; never an authority source.

## Required invariants

- No raw action or raw provider execution is executable through the durable boundary.
- Execution identity is bound to mission, action, governance, contract and validated decision context.
- A durable execution must exist before an external effect can be created.
- Recovery observation must never create an external-effect intent.
- Reconciliation must operate on an existing `UNKNOWN` effect and only after the execution is `RECOVERY_REQUIRED`.
- `UNKNOWN` cannot be treated as success.
- Terminal external-effect evidence is immutable.
- A terminal approval cannot be rewritten.
- Learning cannot create or mutate execution authority.
- Mission and execution terminal state are finalized together by one authoritative durable transition.

## Recovery state machine

```text
RUNNING
  |
  | lease expires / external ambiguity
  v
RECOVERY_REQUIRED
  |
  +---- explicit FAIL/CANCEL ----> terminal execution + terminal mission
  |
  +---- provider reconciliation ---->
             |
             +---- COMPLETED proof --> atomic finalization --> COMPLETED
             |
             +---- FAILED proof -----> terminal failure transition
             |
             +---- UNKNOWN ----------> remain RECOVERY_REQUIRED
```

There is deliberately no generic `CONFIRM` transition from `RECOVERY_REQUIRED`. Success requires evidence from the external system represented by a persisted effect record.

## Concurrency model

Execution and effect claims use conditional durable updates. Only the worker that changes the expected state owns the claim. A competing worker must observe the resulting state and fail closed rather than invoking the provider again.

## What is not authority

`ExecutionResult`, `DurableExecutionLedger`, learning records, agent messages, world-model hypotheses, cached provider responses, and in-memory orchestration state may be useful projections or inputs, but none may independently establish that an external action happened.
