from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    risk_ceiling: int
    min_reversibility: int
    requires_human: bool
    allowed_action_names: tuple[str, ...] = ()


class CapabilityRegistry:
    """Explicit allow-list of capabilities and their minimum governance requirements."""

    _SPECS: dict[str, CapabilitySpec] = {
        "read_email": CapabilitySpec("read_email", 2, 7, False, ("read_email", "list_email")),
        "create_calendar_event": CapabilitySpec("create_calendar_event", 3, 7, False, ("create_calendar_event",)),
        "send_email": CapabilitySpec("send_email", 6, 5, True, ("send_email", "send_application")),
        "modify_github": CapabilitySpec("modify_github", 6, 5, True, ("modify_github", "create_issue", "create_pull_request")),
        "publish_content": CapabilitySpec("publish_content", 6, 5, True, ("publish_content",)),
        "transfer_money": CapabilitySpec("transfer_money", 10, 1, True, ("transfer_money", "wire_money")),
        "delete_account": CapabilitySpec("delete_account", 10, 1, True, ("delete_account",)),
        "legal_filing": CapabilitySpec("legal_filing", 9, 2, True, ("legal_filing",)),
    }

    @classmethod
    def normalize(cls, capability: str) -> str:
        return capability.strip().lower().replace("-", "_").replace(" ", "_")

    @classmethod
    def resolve(cls, capability: str | None) -> CapabilitySpec | None:
        if capability is None:
            return None
        return cls._SPECS.get(cls.normalize(capability))

    @classmethod
    def is_known(cls, capability: str | None) -> bool:
        return capability is not None and cls.resolve(capability) is not None

    @classmethod
    def is_action_compatible(cls, capability: str, action_name: str) -> bool:
        spec = cls.resolve(capability)
        if spec is None:
            return False
        return action_name.strip().lower() in spec.allowed_action_names
