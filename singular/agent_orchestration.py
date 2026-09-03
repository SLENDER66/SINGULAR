"""Deterministic orchestration primitives for SINGULAR's agent workforce.

Agents propose work; policy decides what is worth doing. This module deliberately
contains no model calls and no execution authority. It turns competing work
items into a reproducible priority queue, reducing coordination overhead while
keeping execution behind the validated decision boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class WorkClass(str, Enum):
    SECURITY = "SECURITY"
    CORRECTNESS = "CORRECTNESS"
    INTEGRATION = "INTEGRATION"
    LEARNING = "LEARNING"
    PRODUCT = "PRODUCT"
    REVENUE = "REVENUE"
    PERFORMANCE = "PERFORMANCE"
    RESEARCH = "RESEARCH"
    DOCUMENTATION = "DOCUMENTATION"


@dataclass(frozen=True)
class WorkItem:
    """A bounded piece of work that an agent may propose."""

    id: str
    title: str
    work_class: WorkClass
    impact: float
    confidence: float
    urgency: float
    strategic_value: float
    effort_hours: float
    risk_reduction: float = 0.0
    blocks_revenue: bool = False

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.title.strip():
            raise ValueError("WorkItem id and title cannot be empty")
        for name, value in (
            ("impact", self.impact),
            ("confidence", self.confidence),
            ("urgency", self.urgency),
            ("strategic_value", self.strategic_value),
            ("effort_hours", self.effort_hours),
            ("risk_reduction", self.risk_reduction),
        ):
            if not isfinite(value):
                raise ValueError(f"WorkItem {name} must be finite")
        for name, value in (("impact", self.impact), ("urgency", self.urgency),
                            ("strategic_value", self.strategic_value),
                            ("risk_reduction", self.risk_reduction)):
            if not 0 <= value <= 10:
                raise ValueError(f"WorkItem {name} must be between 0 and 10")
        if not 0 < self.confidence <= 1:
            raise ValueError("WorkItem confidence must be in (0, 1]")
        if self.effort_hours <= 0:
            raise ValueError("WorkItem effort_hours must be positive")

    @property
    def priority_score(self) -> float:
        """Value delivered per unit effort, with explicit risk/revenue bonuses."""
        base = (
            self.impact * 0.30
            + self.urgency * 0.20
            + self.strategic_value * 0.25
            + self.risk_reduction * 0.25
        )
        revenue_bonus = 1.5 if self.blocks_revenue else 1.0
        return base * self.confidence * revenue_bonus / self.effort_hours


@dataclass(frozen=True)
class OrchestrationPolicy:
    max_parallel_work: int = 4
    prioritize_security: bool = True
    prioritize_revenue_blockers: bool = True


class NextBestAction:
    """Select the highest-value bounded work without executing it."""

    def __init__(self, policy: OrchestrationPolicy | None = None) -> None:
        self.policy = policy or OrchestrationPolicy()

    def rank(self, items: tuple[WorkItem, ...]) -> tuple[WorkItem, ...]:
        if len({item.id for item in items}) != len(items):
            raise ValueError("WorkItem ids must be unique")

        def key(item: WorkItem) -> tuple[float, int, int, str]:
            security = int(self.policy.prioritize_security and item.work_class == WorkClass.SECURITY)
            revenue = int(self.policy.prioritize_revenue_blockers and item.blocks_revenue)
            return (item.priority_score, security, revenue, item.id)

        return tuple(sorted(items, key=key, reverse=True))

    def next_batch(self, items: tuple[WorkItem, ...]) -> tuple[WorkItem, ...]:
        return self.rank(items)[: self.policy.max_parallel_work]
