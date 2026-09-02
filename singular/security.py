from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .autopilot import ActionRequest


class ActionTier(str, Enum):
    GREEN = "GREEN"
    ORANGE = "ORANGE"
    RED = "RED"
    BLACK = "BLACK"


@dataclass(frozen=True)
class PolicyDecision:
    tier: ActionTier
    allowed: bool
    requires_human: bool
    reasons: tuple[str, ...]


class ActionPolicy:
    """Defense-in-depth policy. It is stricter than the Governor, never looser."""

    SENSITIVE_KEYWORDS = frozenset({
        "wire_money", "transfer_money", "sign_contract", "delete_account",
        "legal_filing", "send_sensitive_email", "publish_sensitive",
    })

    @classmethod
    def evaluate(cls, action: ActionRequest) -> PolicyDecision:
        name = action.name.lower()
        reasons: list[str] = []
        if action.sensitive or name in cls.SENSITIVE_KEYWORDS:
            return PolicyDecision(ActionTier.BLACK, False, True, ("Opération sensible ou irréversible détectée.",))
        if action.risk >= 8 or action.reversibility <= 2:
            reasons.append("Risque élevé ou faible réversibilité.")
            return PolicyDecision(ActionTier.RED, False, True, tuple(reasons))
        if action.risk >= 5 or action.reversibility < 5:
            reasons.append("Action nécessitant une préparation/validation renforcée.")
            return PolicyDecision(ActionTier.ORANGE, True, True, tuple(reasons))
        return PolicyDecision(ActionTier.GREEN, True, False, ("Action faible risque et suffisamment réversible.",))
