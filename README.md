# SINGULAR

SINGULAR is a governed personal agentic operating system for decision intelligence, execution, learning, and long-term strategy.

## Architecture

`WORLD MODEL → COMMANDER → WORKFORCE → PORTFOLIO → RED TEAM → GOVERNOR → EXECUTION → RESULT → LEARNING → SYSTEM ARCHITECT`

The domain core is deterministic. The OpenAI Agents SDK is isolated behind an optional runtime boundary.

## Governance

- GREEN: low-risk, reversible actions may be automated when explicitly authorized.
- ORANGE: prepare, then request human approval.
- RED: block fail-closed.
- BLACK: sensitive or irreversible categories remain human-controlled.

Financial transfers, contracts, legal filings, account deletion, and sensitive communications are not autonomously executed by core SINGULAR.

## Current version

V3.3 — Durable Agent Core.

Includes governed specialist routing, Red Team gates, defense-in-depth Governor checks, SQLite persistence, restart-safe missions, durable approvals, audit events, and deterministic idempotency primitives.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
```

Optional Agents SDK runtime:

```bash
python -m pip install -e '.[runtime]'
```

See `docs/architecture.md`, `docs/autonomy.md`, `constitution.md`, and `SECURITY.md`.

## Scope

This repository is a production-oriented foundation, not a claim of unrestricted autonomous deployment. Real-world connectors, external side effects, observability infrastructure, and deployment policy must remain explicitly configured and governed.

## License

No open-source license is granted yet. All rights reserved unless otherwise stated by the repository owner.
