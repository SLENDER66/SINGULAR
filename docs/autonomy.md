# Autonomy Policy

## Green
Low-risk, reversible, non-sensitive actions may be automated when explicitly covered by system policy.

## Orange
Medium-risk actions are prepared and surfaced for validation.

## Red
High-risk or low-reversibility actions are blocked from autonomous execution and require human approval.

## Black
Sensitive/irreversible categories (money movement, contracts, legal filings, account deletion, sensitive communications) are never autonomously executed by core SINGULAR.

The Governor remains the execution gate. The policy layer is defense-in-depth and may only make a decision stricter.
