# SINGULAR

[![CI](https://github.com/SLENDER66/SINGULAR/actions/workflows/ci.yml/badge.svg)](https://github.com/SLENDER66/SINGULAR/actions/workflows/ci.yml)

**A governed execution boundary for autonomous agents.**

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
   → outcome ledger          prediction vs. reality, hash-chained
```

Every stage is **reconstructed** at validation time, not trusted. A decision
carrying a favourable report is rejected unless re-running the gate on its own
inputs produces the same report. A decision naming a capability is rejected
unless the artifact fingerprint still matches the code being handed control.

## Run it

```bash
pip install -e '.[dev]'
python examples/governed_http_effect.py
```

```
decision      DEC-DEMO  fingerprint 9e201407fc5f228c…
artifact      aa06b82cc2d6f9a4…  (the code it authorizes)
attested      durably issued; a decision that is not attested cannot execute
executed      COMPLETED  server calls: 1  body: {'message': 'governed'}
replayed      same decision again  ->  server calls still 1
refused       substituted payload  ->  External-effect payload does not match the validated decision.
              server calls still 1: nothing reached the network
```

Real socket, real SQLite, no mocks. Every refusal is the boundary refusing.

## What it guarantees

| | |
|---|---|
| **Fail-closed** | Raw execution entry points deny by default. Ambiguity refuses rather than authorizes. |
| **Exactly once** | An execution lease has one owner. Replaying a decision returns the first result without re-acting. |
| **Ambiguity is not a guess** | A timed-out external effect is quarantined as UNKNOWN. Resolution comes from asking the provider, never from retrying. |
| **Artifact identity** | A capability token means one artifact, durably. An old token plus a new object after a restart is refused. |
| **Tamper-evident** | Decisions, approvals, audit events and outcomes are fingerprinted and re-verified from their own fields, not from a stored hash. |
| **Learning ≠ policy** | Improvements go candidate → artifact → evaluation → human review → activation, each stage bound to the artifact fingerprint. No promotion path touches safety policy. |

Verified by 572 tests, including adversarial cases: forged reports, substituted
handlers and providers, tampered identities, replay, restart, revocation races,
NaN and infinity inputs, and schema version mismatches. The suite passes in
isolation and in randomised order.

## What it does not do

- It is not an agent framework. It governs execution; it does not plan or reason.
- One real provider ships today (HTTP). Everything else is yours to write.
- Capability fingerprints identify code and closure captures — not what a
  provider instance holds in its attributes. The limit is stated and tested.
- Human approval is currently not an authorization channel: escalated actions
  cannot cross the boundary. That is an open design decision, not an oversight.

## Status

Working and tested, not yet used in production by anyone. Built as a single-user
system; the parts worth reusing are the boundary, the attestation store, the
capability registry and the outcome ledger.

If you deploy agents and any of the four questions at the top is one you cannot
answer today, I would genuinely like to hear how you handle it.

## Layout

```
singular/execution.py                  durable execution engine
singular/validated_trajectory_decision.py   the authorization contract
singular/validated_execution.py        strict boundary adapter
singular/decision_attestation.py       durable issuance and revocation
singular/execution_capability.py       artifact identity for executables
singular/effects.py                    external-effect coordinator
singular/providers/                    real providers
singular/outcome_ledger.py             predictions vs. outcomes
singular/improvement_registry.py       governed learning lifecycle
singular/journal.py                    decision journal, the tool its author uses
docs/                                  authority model, boundary design
attic/                                 parked: what the boundary does not need
```

Licence: see repository. `constitution.md` holds the design principles this is
built to satisfy.
