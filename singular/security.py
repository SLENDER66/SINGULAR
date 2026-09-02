from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .autopilot import ActionRequest
from .capabilities import CapabilityRegistry


class ActionTier(str, Enum):
    GREEN = "GREEN"
    ORANGE = "ORANGE"
    RED = "RED"
    BLACK = "BLACK"


@dataclass(frozen=True)
class PolicyDecision:
    tier: ActionTier
    can_prepare: bool
    can_execute: bool
    requires_human: bool
    reasons: tuple[str, ...]

    @property
    def allowed(self) -> bool:
        """Compatibility view: policy permits at least preparation."""
        return self.can_prepare


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

        if action.capability is not None:
            capability = CapabilityRegistry.resolve(action.capability)
            if capability is None:
                return PolicyDecision(
                    ActionTier.BLACK,
                    False,
                    False,
                    True,
                    ("Capacité inconnue : autorisation refusée par défaut.",),
                )
            if not CapabilityRegistry.is_action_compatible(action.capability, name):
                return PolicyDecision(
                    ActionTier.BLACK,
                    False,
                    False,
                    True,
                    ("La capacité déclarée ne correspond pas à l'action demandée.",),
                )
            if action.risk > capability.risk_ceiling or action.reversibility < capability.min_reversibility:
                return PolicyDecision(
                    ActionTier.RED,
                    False,
                    False,
                    True,
                    ("Les paramètres de risque dépassent les limites de la capacité.",),
                )
            if capability.requires_human:
                return PolicyDecision(
                    ActionTier.ORANGE,
                    True,
                    True,
                    True,
                    (f"Capacité {capability.name} soumise à validation humaine.",),
                )

        if action.sensitive or name in cls.SENSITIVE_KEYWORDS:
            return PolicyDecision(
                ActionTier.BLACK,
                False,
                False,
                True,
                ("Opération sensible ou irréversible détectée.",),
            )
        if action.risk >= 8 or action.reversibility <= 2:
            reasons.append("Risque élevé ou faible réversibilité.")
            return PolicyDecision(ActionTier.RED, False, False, True, tuple(reasons))
        if action.risk >= 5 or action.reversibility < 5:
            reasons.append("Action nécessitant une préparation/validation renforcée.")
            return PolicyDecision(ActionTier.ORANGE, True, True, True, tuple(reasons))
        return PolicyDecision(
            ActionTier.GREEN,
            can_prepare=True,
            can_execute=True,
            requires_human=False,
            reasons=("Action faible risque et suffisamment réversible.",),
        )
