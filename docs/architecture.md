# SINGULAR Architecture

Two layers, deliberately separated: one that thinks, and one that lets something
happen. The whole design is the boundary between them.

## The execution chain

```text
domain state
   → HumanOptimization        what would actually help
   → TrajectoryOptimization   what is worth doing together, under a capacity budget
   → ActionPolicy + Governor  what this action is allowed to be
   → RedTeamGate              why this might be wrong
   → GlobalDecisionGate       one PROCEED, or a refusal with reasons
   → ValidatedTrajectoryDecision
   → DecisionAttestationStore durably issued, revocable, expiring
   → ExecutionCapability      which artifact, by fingerprint
   → execution lease          exactly one owner
   → provider                 the world changes
   → OutcomeLedger            prediction against reality, hash-chained
```

Every stage is **reconstructed** at validation time rather than trusted. A
decision carrying a favourable report is refused unless re-running the gate on
its own inputs produces that same report; a decision naming a capability is
refused unless the artifact fingerprint still matches the code about to be
handed control. `docs/VALIDATED_EXECUTION_BOUNDARY.md` details the artifact,
`docs/AUTHORITY_MODEL.md` details what counts as proof that something happened.

## The observation layer

```text
journal (what you predicted)
   → NoticeEngine             what today's report says
   → the Sage                 web app, and a native iPhone app
```

`singular/sage/` reads the journal and produces an advisory report: what is
waiting for a verdict, where stated confidence misses, which rung of the
constitution is being neglected. It computes; it never authorizes.
`tests/test_sage_isolation.py` refuses any import of the execution boundary from
that package, so a new feature cannot quietly turn an HTTP request into an
action on the world. `ios/SingularSage/` is the same engine in Swift, pinned to
this one by generated vectors.

## The invariant both layers serve

```text
INTELLIGENCE ≠ DECISION ≠ AUTHORIZATION ≠ EXECUTION
LEARNING ≠ SAFETY POLICY
```

An agent may reason. An engine may optimise. A model may learn. None of them
acquires execution authority it was not explicitly granted. The improvement
lifecycle (`singular/improvement_registry.py`) binds candidate → artifact →
fingerprint → evaluation → human review → activation, and no stage of it can
reach a safety-critical target: which targets are safety-critical is derived
from the target's own name, never declared by the proposal.

## Dependencies

The domain core is deterministic and runs without an LLM. The OpenAI Agents SDK
is isolated behind `singular.production_runtime` (optional extra `runtime`), so
model and provider concerns do not leak into the decision model. `singular/sage/`
uses the standard library alone.

System evolution stays proposal-based: the System Architect may recommend
changes; it cannot silently modify production behaviour.
