# attic

Code parked here is not part of SINGULAR and is not imported by it. Nothing is
deleted — it stays in the repository, and in its history, because throwing work
away and admitting it did not fit are different things.

## Why these left

The README describes one thing: a governed execution boundary for autonomous
agents. The package contradicted it. Alongside the boundary sat eighteen modules
about wealth, portfolios, empires and patrimony, plus two earlier stacked
versions of the whole system. A reader arriving at `wealth_engine.py` and
`patrimony_engine.py` reasonably concluded the project did not know what it was.

They also did not work in the sense that matters. Every one is a scoring
function over hand-constructed dataclasses: no data source feeds them, no
execution path consumes them, and no decision anywhere reads their output. They
rank things nobody asked them to rank.

## What is here

**Economic and empire verticals** — `economic_control`, `economic_sequence`,
`enterprise_core`, `wealth_engine`, `empire_engine`, `patrimony_engine`,
`portfolio`, `portfolio_reallocation`, `capital_allocation`, `cashflow_engine`,
`rapid_wealth`, `opportunity_engine`, `opportunity_adapter`, `generational`,
`elite`, `v16_workforce`.

**Earlier whole-system versions** — `v2_empire`, `v2_1_control`.

**Unused advisory layers and stubs** — `temporal_advisor`, `value_evolution`,
`human_optimizer`, `openai_runtime` (25 lines that build an agent object nothing
calls), `demo`.

Their tests moved with them and still pass if run directly; they are outside
`testpaths` so the suite does not collect them.

## Bringing something back

`git mv attic/singular/<module>.py singular/` and re-export it from
`singular/__init__.py`. Nothing else has to change: nothing in the package
depends on any of this, which is how it could leave in one step.
