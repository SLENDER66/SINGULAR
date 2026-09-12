# AZAZEL

[![CI](https://github.com/SLENDER66/SINGULAR/actions/workflows/ci.yml/badge.svg)](https://github.com/SLENDER66/SINGULAR/actions/workflows/ci.yml)

**AZAZEL — powered by the SINGULAR governed execution core.**

SINGULAR is the internal authority and execution-security core. JARVIS is the
user-facing proposal/runtime layer. The final product presented to users will
be called **AZAZEL**.

An agent decides something. Between that decision and the moment it changes
something in the world, SINGULAR requires a durable, verifiable authorization —
and refuses when it cannot reconstruct one.

## The problem

Teams deploying agents can usually answer *what the agent did*. They usually
cannot answer:

- what exactly was it authorized to do, and by which check?
- was that authorization still valid at the moment it acted?
- did it act once, or twice, or not at all?
- is the code that ran the code that was approved?

Logging after the fact does not answer these. They have to be structural.

## AZAZEL architecture: JARVIS + SINGULAR

JARVIS is the user-facing interface and proposal/runtime layer. It is **not a
second authority** and it does not execute tools directly. AZAZEL is the final
product identity; SINGULAR remains the governed execution core.

```
THOMAS
  ↓
AZAZEL / JARVIS / Claude
  ↓  proposal only
SINGULAR
  ↓
World Model / Mission / Trajectory / Decision
  ↓
Governor
  ↓
ValidatedTrajectoryDecision + durable attestation
  ↓
Execution Boundary
  ↓
Tool / external effect
  ↓
Independent verification
  ↓
Audit + outcome + memory
```

The invariant is simple:

> **JARVIS proposes; SINGULAR decides; Governor authorizes; Tool executes;
> Verifier verifies; Audit records; Memory learns.**

Claude cannot choose a governance capability, execution target, verifier,
approval, policy or permission. Model output is treated as untrusted input and
bounded before it reaches SINGULAR.

### CLI

The governed front door is available after installation:

```bash
python3 -m pip install -e ".[dev]"
singular-jarvis "Inspect the repository"
singular-jarvis "Inspect the repository" --route
```

The CLI can propose work and create a governed mission/decision, but it has no
`execute` command. Effects remain behind the validated decision service and
execution boundary. The `--route` path therefore cannot turn a model proposal
into an effect by itself.

## The chain

```
domain state
   → human optimization      what would actually help
   → trajectory portfolio    what is worth doing, under a capacity budget
   → policy + governor       what this action is allowed to be
   → red team gate           why this might be wrong
   → GlobalDecisionGate      one PROCEED, or a refusal with reasons
   → ValidatedTrajectoryDecision
   → durable attestation     issued, revocable, expiring
   → capability              which code, bound to an artifact fingerprint
   → execution lease         exactly one owner
   → external effect         the world changes
   → independent verification
   → audit + outcome ledger  prediction vs. reality, hash-chained
```

Every stage is **reconstructed** at validation time, not trusted. A decision
carrying a favourable report is rejected unless re-running the gate on its own
inputs produces the same report. A decision naming a capability is rejected
unless the artifact fingerprint still matches the code being handed control.

## What it guarantees

| | |
|---|---|
| **Fail-closed** | Raw execution entry points deny by default. Ambiguity refuses rather than authorizes. |
| **Exactly once** | An execution lease has one owner. Replaying a decision returns the first result without re-acting. |
| **Ambiguity is not a guess** | A timed-out external effect is quarantined as UNKNOWN. Resolution comes from asking the provider, never from retrying. |
| **Artifact identity** | A capability token means one artifact, durably. An old token plus a new object after a restart is refused. |
| **Tamper-evident** | Decisions, approvals, audit events and outcomes are fingerprinted and re-verified from their own fields, not from a stored hash. |
| **Learning ≠ policy** | Improvements go candidate → artifact → evaluation → human review → activation, each stage bound to the artifact fingerprint. No promotion path touches safety policy. |
| **JARVIS is asymmetric** | Proposal and governed routing are exposed; direct execution is not. LLM-selected authority is ignored. |

The validated execution core is adversarially tested for forged reports,
substituted handlers and providers, same-named implementations differing in
constants, tampered identities, replay, restart, revocation races, torn reads,
NaN and infinity inputs, schema mismatches and stale execution state.

## What it does not do

- It is not an unrestricted agent framework. Governance and execution authority
  remain in SINGULAR.
- Claude is a proposal provider, not an authority. API credentials are read only
  from `ANTHROPIC_API_KEY` and are never included in audit output.
- Capability fingerprints identify the whole code object, a class's attributes,
  closure captures and default arguments — but not what a provider *instance*
  holds unless it declares `artifact_identity()`, and not what a global name
  resolves to. Both limits are explicit rather than hidden.
- Human approval is currently not an authorization channel: escalated actions
  cannot cross the validated execution boundary. That is an intentional open
  design decision, not an accidental bypass.

## Status

The current JARVIS slice is implemented on top of SINGULAR's existing authority
model. AZAZEL is the final product name; SINGULAR remains the internal governed
core. CI validation is required after each change; a green test suite is not a
reason to bypass the next audit or red-team pass.

The project is deliberately built in layers: the face can evolve quickly while
the authority boundary remains conservative. Neuroscience and other evidence
sources belong in the evidence layer; they do not create a new authority or
clinical inference engine.

## Layout

```
singular/jarvis/                     JARVIS proposal/runtime/CLI
singular/execution.py                durable execution engine
singular/validated_trajectory_decision.py   authorization contract
singular/validated_execution.py      strict boundary adapter
singular/decision_attestation.py     durable issuance and revocation
singular/execution_capability.py     artifact identity for executables
singular/effects.py                  external-effect coordinator
singular/providers/                  real providers
singular/outcome_ledger.py           predictions vs. outcomes
singular/improvement_registry.py     governed learning lifecycle
singular/journal.py                  decision journal
singular/sage/                       observation/reporting layer
singular/analyse.py                  optional model faculties
singular/offres.py                   isolated proposal faculties
singular/parle.py                    communication layer
ios/SingularSage/                    native iPhone app

docs/                                authority model and boundary design
attic/                               parked material
```

Licence: MIT, see `LICENSE`. `constitution.md` holds the design principles this is
built to satisfy.
