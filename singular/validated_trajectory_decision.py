"""Immutable, tamper-evident authorization contract for validated trajectories."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from hashlib import sha256
from math import isfinite
from typing import Any

from .autopilot import ActionRequest, Autonomy, DelegationContract, Governor, GovernorDecision
from .global_control import GlobalDecisionReport
from .human_optimization import HumanOptimizationReport
from .security import ActionPolicy, PolicyDecision
from .trajectory import TrajectoryAssessment, TrajectoryDecision
from .trajectory_optimization import TrajectoryPortfolio
from .v32_governed_core import RedTeamFinding, RedTeamGate


@dataclass(frozen=True)
class ValidatedActionRequest:
    """Immutable snapshot of the ActionRequest admitted by a validated decision."""

    id: str
    name: str
    description: str
    impact: float
    risk: float
    reversibility: float
    requires_human: bool
    sensitive: bool
    contract_id: str | None
    capability: str | None

    @classmethod
    def from_action(cls, action: ActionRequest) -> "ValidatedActionRequest":
        return cls(action.id, action.name, action.description, action.impact, action.risk, action.reversibility,
                   action.requires_human, action.sensitive, action.contract_id, action.capability)

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip() or not self.description.strip():
            raise ValueError("validated action id, name and description cannot be empty")
        for name, value in (("impact", self.impact), ("risk", self.risk), ("reversibility", self.reversibility)):
            if not isfinite(value) or not 0 <= value <= 10:
                raise ValueError(f"validated action {name} must be finite and between 0 and 10")

    def to_action(self) -> ActionRequest:
        return ActionRequest(name=self.name, description=self.description, impact=self.impact, risk=self.risk,
                             reversibility=self.reversibility, requires_human=self.requires_human,
                             sensitive=self.sensitive, contract_id=self.contract_id, id=self.id, capability=self.capability)


@dataclass(frozen=True)
class ValidatedTrajectoryDecision:
    """A trajectory-backed decision accepted by the execution boundary.

    The artifact binds decision evidence to the exact execution target. External
    effects additionally bind provider implementation, provider name, operation,
    and payload fingerprint, preventing TOCTOU substitution and replay.
    """

    decision_id: str
    authorized_actions: tuple[ValidatedActionRequest, ...]
    action_to_intervention: tuple[tuple[str, str], ...]
    human_optimization: HumanOptimizationReport
    trajectory_portfolio: TrajectoryPortfolio
    trajectory_assessment: TrajectoryAssessment
    global_report: GlobalDecisionReport
    contract: DelegationContract
    policy: PolicyDecision
    red_team_findings: tuple[RedTeamFinding, ...]
    governor: GovernorDecision
    execution_target: str
    execution_kind: str
    provider_name: str | None
    provider_target: str | None
    operation: str | None
    payload_fingerprint: str | None
    context_fingerprint: str

    @classmethod
    def create(cls, *, decision_id: str, actions: tuple[ActionRequest, ...], action_to_intervention: tuple[tuple[str, str], ...],
               human_optimization: HumanOptimizationReport | None, trajectory_portfolio: TrajectoryPortfolio | None,
               trajectory_assessment: TrajectoryAssessment | None, global_report: GlobalDecisionReport | None,
               contract: DelegationContract | None, policy: PolicyDecision | None,
               red_team_findings: tuple[RedTeamFinding, ...] | None, governor: GovernorDecision | None,
               execution_target: str, execution_kind: str = "handler", provider_name: str | None = None,
               provider_target: str | None = None, operation: str | None = None,
               payload_fingerprint: str | None = None) -> "ValidatedTrajectoryDecision":
        required = {"human_optimization": human_optimization, "trajectory_portfolio": trajectory_portfolio,
                    "trajectory_assessment": trajectory_assessment, "global_report": global_report,
                    "contract": contract, "policy": policy, "red_team_findings": red_team_findings, "governor": governor}
        for name, value in required.items():
            if value is None:
                raise ValueError(f"{name} is required")
        snapshots = tuple(ValidatedActionRequest.from_action(action) for action in actions)
        payload = cls._payload(decision_id, snapshots, action_to_intervention, human_optimization, trajectory_portfolio,
                               trajectory_assessment, global_report, contract, policy, red_team_findings, governor,
                               execution_target, execution_kind, provider_name, provider_target, operation, payload_fingerprint)
        return cls(decision_id, snapshots, action_to_intervention, human_optimization, trajectory_portfolio,
                   trajectory_assessment, global_report, contract, policy, red_team_findings, governor,
                   execution_target, execution_kind, provider_name, provider_target, operation, payload_fingerprint,
                   _fingerprint(payload))

    def __post_init__(self) -> None:
        self._validate()
        expected = _fingerprint(self._payload(self.decision_id, self.authorized_actions, self.action_to_intervention,
                                              self.human_optimization, self.trajectory_portfolio, self.trajectory_assessment,
                                              self.global_report, self.contract, self.policy, self.red_team_findings,
                                              self.governor, self.execution_target, self.execution_kind, self.provider_name,
                                              self.provider_target, self.operation, self.payload_fingerprint))
        if self.context_fingerprint != expected:
            raise ValueError("validated trajectory decision context fingerprint is invalid")

    def verify(self) -> bool:
        try:
            self._validate()
            expected = _fingerprint(self._payload(self.decision_id, self.authorized_actions, self.action_to_intervention,
                                                  self.human_optimization, self.trajectory_portfolio, self.trajectory_assessment,
                                                  self.global_report, self.contract, self.policy, self.red_team_findings,
                                                  self.governor, self.execution_target, self.execution_kind, self.provider_name,
                                                  self.provider_target, self.operation, self.payload_fingerprint))
        except (TypeError, ValueError):
            return False
        return self.context_fingerprint == expected

    def _validate(self) -> None:
        if not self.decision_id.strip():
            raise ValueError("decision_id cannot be empty")
        if not self.execution_target.strip():
            raise ValueError("execution_target cannot be empty")
        if self.execution_kind not in {"handler", "external_effect"}:
            raise ValueError("execution_kind must be handler or external_effect")
        if self.execution_kind == "handler":
            if any(value is not None for value in (self.provider_name, self.provider_target, self.operation, self.payload_fingerprint)):
                raise ValueError("handler decisions cannot carry external-effect bindings")
        else:
            if not self.provider_name or not self.provider_target or not self.operation or not self.payload_fingerprint:
                raise ValueError("external-effect decisions require provider, provider target, operation and payload fingerprint")
        if self.global_report.decision != "PROCEED":
            raise ValueError("only a PROCEED global report can create a validated trajectory decision")
        if self.global_report.requires_human:
            raise ValueError("a global report requiring human review cannot be validated")
        if self.global_report.trajectory != self.trajectory_assessment:
            raise ValueError("global report must carry the validated trajectory assessment")
        if self.global_report.human_optimization != self.human_optimization:
            raise ValueError("global report must carry the validated human optimization report")
        if self.trajectory_assessment.decision is not TrajectoryDecision.PROCEED:
            raise ValueError("trajectory assessment must be PROCEED")
        if self.trajectory_assessment.human_review:
            raise ValueError("trajectory assessment requiring human review cannot be validated")
        if not self.authorized_actions:
            raise ValueError("at least one authorized action is required")
        action_ids = tuple(action.id for action in self.authorized_actions)
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("authorized action ids must be unique")
        if self.global_report.action_id not in action_ids:
            raise ValueError("global report action must be one of the authorized actions")
        if self.governor.action_id not in action_ids:
            raise ValueError("governor decision must target an authorized action")
        if self.governor.mode not in {Autonomy.EXECUTE_REVERSIBLE, Autonomy.EXECUTE_AUTHORIZED}:
            raise ValueError("governor decision must explicitly authorize execution")
        if self.global_report.governor_mode is not self.governor.mode:
            raise ValueError("global report governor mode must match the validated governor decision")
        if self.global_report.objective != self.contract.objective:
            raise ValueError("global report objective must match the execution contract")
        if not self.policy.can_prepare or not self.policy.can_execute or self.policy.requires_human:
            raise ValueError("policy must explicitly permit execution without pending human review")
        if self.policy.tier.value != self.global_report.policy_tier:
            raise ValueError("policy tier must match the global report")
        if self.policy.requires_human != self.global_report.policy_requires_human:
            raise ValueError("policy human-review state must match the global report")
        if self.red_team_findings != self.global_report.red_team_findings:
            raise ValueError("red-team findings must match the global report")
        if any(finding.blocking for finding in self.red_team_findings):
            raise ValueError("blocking red-team findings cannot create a validated decision")
        mappings = dict(self.action_to_intervention)
        if len(mappings) != len(self.action_to_intervention):
            raise ValueError("action-to-intervention mappings must be unique by action id")
        if set(mappings) != set(action_ids):
            raise ValueError("every authorized action must map to exactly one intervention")
        portfolio_ids = {candidate.intervention_id for candidate in self.trajectory_portfolio.candidates}
        if not portfolio_ids:
            raise ValueError("trajectory portfolio cannot be empty")
        if not set(mappings.values()) <= portfolio_ids:
            raise ValueError("every authorized action must belong to the validated trajectory portfolio")
        human_ids = {candidate.intervention_id for candidate in self.human_optimization.candidates}
        if not portfolio_ids <= human_ids:
            raise ValueError("trajectory portfolio candidates must originate from human optimization")
        if any(candidate.human_review for candidate in self.trajectory_portfolio.candidates):
            raise ValueError("portfolio candidates requiring human review cannot be validated")
        if any(candidate.disposition.name != "PROPOSE" for candidate in self.trajectory_portfolio.candidates):
            raise ValueError("only proposed portfolio candidates can be validated")
        if not self.contract.mission_id.strip() or not self.contract.objective.strip() or not self.contract.expected_result.strip():
            raise ValueError("contract fields cannot be empty")
        if self.contract.autonomy not in {Autonomy.EXECUTE_REVERSIBLE, Autonomy.EXECUTE_AUTHORIZED}:
            raise ValueError("contract must explicitly permit execution")
        for action in self.authorized_actions:
            if action.contract_id != self.contract.mission_id:
                raise ValueError("authorized action must be bound to the execution contract")
        selected_action = next(action for action in self.authorized_actions if action.id == self.global_report.action_id)
        materialized = selected_action.to_action()
        expected_policy = ActionPolicy.evaluate(materialized)
        if self.policy != expected_policy:
            raise ValueError("validated policy does not match the authorized action")
        expected_governor = Governor.evaluate(materialized, self.contract)
        if self.governor != expected_governor:
            raise ValueError("validated governor decision does not match the authorized action and contract")
        expected_red_team = RedTeamGate().inspect(materialized, self.contract)
        if self.red_team_findings != expected_red_team:
            raise ValueError("validated red-team findings do not match the authorized action and contract")
        _validate_finite("human capacity budget", self.human_optimization.capacity_budget, minimum=0)
        _validate_finite("human capacity used", self.human_optimization.capacity_used, minimum=0)
        _validate_finite("human capacity remaining", self.human_optimization.capacity_remaining, minimum=0)
        _validate_finite("trajectory portfolio objective", self.trajectory_portfolio.objective)
        _validate_finite("trajectory portfolio capacity used", self.trajectory_portfolio.capacity_used, minimum=0)
        _validate_finite("trajectory portfolio capacity remaining", self.trajectory_portfolio.capacity_remaining, minimum=0)
        _validate_finite("trajectory portfolio interaction effect", self.trajectory_portfolio.interaction_effect)
        _validate_finite("trajectory score", self.trajectory_assessment.score, minimum=-1, maximum=1)
        _validate_finite("trajectory weighted contribution", self.trajectory_assessment.weighted_contribution)
        if self.contract.budget_limit is not None:
            _validate_finite("contract budget limit", self.contract.budget_limit, minimum=0)
        for candidate in self.human_optimization.candidates + self.trajectory_portfolio.candidates:
            _validate_finite("candidate score", candidate.score)
            _validate_finite("candidate expected global gain", candidate.expected_global_gain)

    @staticmethod
    def _payload(decision_id: str, actions: tuple[ValidatedActionRequest, ...], action_to_intervention: tuple[tuple[str, str], ...],
                 human_optimization: HumanOptimizationReport, trajectory_portfolio: TrajectoryPortfolio,
                 trajectory_assessment: TrajectoryAssessment, global_report: GlobalDecisionReport, contract: DelegationContract,
                 policy: PolicyDecision, red_team_findings: tuple[RedTeamFinding, ...], governor: GovernorDecision,
                 execution_target: str, execution_kind: str, provider_name: str | None, provider_target: str | None,
                 operation: str | None, payload_fingerprint: str | None) -> dict[str, Any]:
        return {"decision_id": decision_id, "authorized_actions": actions, "action_to_intervention": tuple(sorted(action_to_intervention)),
                "human_optimization": human_optimization, "trajectory_portfolio": trajectory_portfolio,
                "trajectory_assessment": trajectory_assessment, "global_report": global_report, "contract": contract,
                "policy": policy, "red_team_findings": red_team_findings, "governor": governor,
                "execution_target": execution_target, "execution_kind": execution_kind, "provider_name": provider_name,
                "provider_target": provider_target, "operation": operation, "payload_fingerprint": payload_fingerprint}


def _validate_finite(name: str, value: float, *, minimum: float | None = None, maximum: float | None = None) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}")


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(_normalize(payload), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _normalize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _normalize(item) for key, item in asdict(value).items()}  # type: ignore[arg-type]
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("fingerprinted numeric values must be finite")
    return value


def payload_fingerprint(payload: Any) -> str:
    """Canonical fingerprint used to bind an external-effect payload."""
    canonical = json.dumps(_normalize(payload), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


__all__ = ["ValidatedActionRequest", "ValidatedTrajectoryDecision", "payload_fingerprint"]
