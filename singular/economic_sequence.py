from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class EconomicStage(str, Enum):
    CASH = "CASH"
    CAPACITY = "CAPACITY"
    RECURRING = "RECURRING"
    OWNERSHIP = "OWNERSHIP"
    CAPITAL = "CAPITAL"
    COMPOUNDING = "COMPOUNDING"
    CONTROL = "CONTROL"
    INSTITUTION = "INSTITUTION"
    TRANSMISSION = "TRANSMISSION"


@dataclass(frozen=True)
class EconomicStep:
    """A recommended step in an economic sequence; never an execution command."""

    id: str
    stage: EconomicStage
    expected_cash: float = 0.0
    expected_value: float = 0.0
    probability: float = 0.0
    risk: float = 0.0
    capacity_required: float = 0.0
    reversibility: float = 1.0
    ownership_value: float = 0.0
    compounding_value: float = 0.0
    prerequisites: tuple[str, ...] = ()
    satisfied_prerequisites: tuple[str, ...] = ()
    lesson_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("id must be non-empty")
        for name, value in (
            ("expected_cash", self.expected_cash),
            ("expected_value", self.expected_value),
            ("probability", self.probability),
            ("risk", self.risk),
            ("capacity_required", self.capacity_required),
            ("reversibility", self.reversibility),
            ("ownership_value", self.ownership_value),
            ("compounding_value", self.compounding_value),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.expected_cash < 0 or self.expected_value < 0:
            raise ValueError("expected cash/value cannot be negative")
        if not 0 <= self.probability <= 1:
            raise ValueError("probability must be within [0, 1]")
        if not 0 <= self.risk <= 10:
            raise ValueError("risk must be within [0, 10]")
        if self.capacity_required < 0:
            raise ValueError("capacity_required cannot be negative")
        if not 0 <= self.reversibility <= 10:
            raise ValueError("reversibility must be within [0, 10]")


@dataclass(frozen=True)
class EconomicSequence:
    """Ordered economic strategy with explicit gates and no execution authority."""

    steps: tuple[EconomicStep, ...]
    blocked_steps: tuple[str, ...]
    score: float
    rationale: tuple[str, ...]
    method: str = "DETERMINISTIC_STAGE_GATED"


class EconomicSequenceEngine:
    """Prefer the best next executable stage over an attractive but premature one."""

    STAGE_ORDER = tuple(EconomicStage)

    @staticmethod
    def _score(step: EconomicStep, failure_lesson_bonus: float = 0.0) -> float:
        expected = step.expected_cash + step.expected_value
        ownership = 1.0 + max(step.ownership_value, 0.0) / 10.0
        compounding = 1.0 + max(step.compounding_value, 0.0) / 10.0
        safety = (0.5 + step.reversibility / 20.0) / (1.0 + step.risk / 10.0)
        return round(expected * step.probability * ownership * compounding * safety + failure_lesson_bonus, 6)

    @classmethod
    def plan(
        cls,
        steps: list[EconomicStep],
        *,
        available_capacity: float,
        completed_stages: tuple[EconomicStage, ...] = (),
        failure_lesson_ids: tuple[str, ...] = (),
    ) -> EconomicSequence:
        if not isfinite(available_capacity) or available_capacity < 0:
            raise ValueError("available_capacity must be finite and non-negative")
        ordered = sorted(steps, key=lambda item: (cls.STAGE_ORDER.index(item.stage), item.id))
        if len({item.id for item in ordered}) != len(ordered):
            raise ValueError("step ids must be unique")

        completed = {stage.value for stage in completed_stages}
        completed.update(stage.name for stage in completed_stages)
        lessons = set(failure_lesson_ids)
        eligible: list[tuple[float, EconomicStep]] = []
        blocked: list[str] = []
        for step in ordered:
            effective_satisfied = completed | set(step.satisfied_prerequisites)
            prerequisites_ok = all(prerequisite in effective_satisfied for prerequisite in step.prerequisites)
            if step.capacity_required > available_capacity or not prerequisites_ok:
                blocked.append(step.id)
                continue
            lesson_bonus = 0.05 if lessons.intersection(step.lesson_ids) else 0.0
            eligible.append((cls._score(step, lesson_bonus), step))

        selected: list[EconomicStep] = []
        remaining_capacity = available_capacity
        selected_score = 0.0
        for stage in cls.STAGE_ORDER:
            candidates = [
                (score, item) for score, item in eligible
                if item.stage is stage and item.capacity_required <= remaining_capacity
            ]
            if not candidates:
                continue
            winner_score, winner = max(candidates, key=lambda item: (item[0], item[1].id))
            selected.append(winner)
            selected_score = winner_score
            break

        rationale = ["SEQUENCE_BEATS_STATIC_RANKING", "EARLIEST_UNLOCKED_STAGE_FIRST", "RECOMMENDATION_ONLY"]
        if selected:
            rationale.append(f"NEXT_STAGE={selected[0].stage.value}")
        else:
            rationale.append("NO_ELIGIBLE_NEXT_STEP")
        return EconomicSequence(
            steps=tuple(selected),
            blocked_steps=tuple(blocked),
            score=round(selected_score, 6),
            rationale=tuple(rationale),
        )
