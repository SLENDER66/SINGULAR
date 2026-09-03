from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from .autopilot import ActionRequest
from .global_control import GlobalDecisionGate, GlobalDecisionReport
from .learning import Forecast
from .world_model import WorldModel


class DecisionStatus(str, Enum):
    PROPOSED = "PROPOSED"
    REVIEW = "REVIEW"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class DecisionOption:
    """A candidate action; selecting it never authorizes execution."""

    id: str
    action: ActionRequest
    rationale: str = ""
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionContext:
    """Decision inputs with explicit epistemic boundaries."""

    decision_id: str
    objective: str
    options: tuple[DecisionOption, ...]
    forecasts: tuple[Forecast, ...] = ()
    assumptions: tuple[str, ...] = ()
    world_model: WorldModel | None = None

    def __post_init__(self) -> None:
        if not self.decision_id.strip():
            raise ValueError("decision_id cannot be empty")
        if not self.objective.strip():
            raise ValueError("objective cannot be empty")
        if not self.options:
            raise ValueError("at least one decision option is required")
        ids = [option.id for option in self.options]
        if len(ids) != len(set(ids)):
            raise ValueError("decision option ids must be unique")
        forecast_ids = [forecast.id for forecast in self.forecasts]
        if len(forecast_ids) != len(set(forecast_ids)):
            raise ValueError("forecast ids must be unique")


@dataclass(frozen=True)
class DecisionRecommendation:
    """A bounded recommendation. It is not an authorization or execution order."""

    decision_id: str
    objective: str
    status: DecisionStatus
    selected_option_id: str | None
    reports: tuple[GlobalDecisionReport, ...]
    rationale: str
    confidence: float
    unresolved_questions: tuple[str, ...] = ()

    @property
    def requires_human(self) -> bool:
        return self.status is not DecisionStatus.PROPOSED or any(
            report.requires_human for report in self.reports
        )

    @property
    def authorized(self) -> bool:
        """Always false: authorization is deliberately outside this engine."""
        return False


class DecisionEngine:
    """Select among prepared options while preserving governance boundaries."""

    def __init__(self, gate: GlobalDecisionGate | None = None) -> None:
        self.gate = gate or GlobalDecisionGate()

    def recommend(self, context: DecisionContext) -> DecisionRecommendation:
        reports = tuple(
            self.gate.evaluate(
                context.objective,
                option.action,
                world_model=context.world_model,
            )
            for option in context.options
        )

        viable = [
            (option, report)
            for option, report in zip(context.options, reports)
            if report.decision != "BLOCK"
        ]
        unresolved: list[str] = []
        if context.world_model is not None:
            unresolved.extend(
                f"WORLD_MODEL:UNKNOWN:{key}"
                for key in sorted(context.world_model.unknowns())
            )

        if not viable:
            return DecisionRecommendation(
                context.decision_id,
                context.objective,
                DecisionStatus.BLOCKED,
                None,
                reports,
                "Aucune option ne satisfait les garde-fous actuels.",
                0.0,
                tuple(dict.fromkeys(unresolved)),
            )

        ranked = sorted(
            viable,
            key=lambda item: self._score(item[0].action),
            reverse=True,
        )
        selected, selected_report = ranked[0]
        if selected_report.requires_human:
            unresolved.append(f"HUMAN_REVIEW:{selected.id}")
        if any(report.decision == "REVIEW" for _, report in viable):
            unresolved.append("ALTERNATIVES_REQUIRE_REVIEW")

        confidence = self._confidence(selected_report, context.forecasts)
        status = (
            DecisionStatus.REVIEW
            if unresolved or selected_report.decision == "REVIEW"
            else DecisionStatus.PROPOSED
        )
        rationale = (
            f"Option {selected.id} sélectionnée par classement déterministe; "
            "la recommandation ne constitue ni une autorisation ni une exécution."
        )
        return DecisionRecommendation(
            context.decision_id,
            context.objective,
            status,
            selected.id,
            reports,
            rationale,
            confidence,
            tuple(dict.fromkeys(unresolved)),
        )

    @staticmethod
    def _score(action: ActionRequest) -> float:
        if not all(isfinite(value) for value in (action.impact, action.risk, action.reversibility)):
            return float("-inf")
        return round(
            action.impact * (0.5 + action.reversibility / 20) / (1 + action.risk),
            6,
        )

    @staticmethod
    def _confidence(
        report: GlobalDecisionReport, forecasts: tuple[Forecast, ...]
    ) -> float:
        base = 0.9 if report.decision == "PROCEED" else 0.55
        if report.requires_human:
            base -= 0.2
        if forecasts:
            base *= sum(forecast.confidence for forecast in forecasts) / len(forecasts)
        return round(max(0.0, min(1.0, base)), 4)
