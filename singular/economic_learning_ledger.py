from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from enum import Enum
from typing import Any

from .durable import DurableStore
from .economic_learning import EconomicLearningCycle


def _json_default(value: Any) -> str:
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Unsupported value for canonical serialization: {type(value)!r}")


def _canonical_cycle(cycle: EconomicLearningCycle) -> str:
    return json.dumps(
        asdict(cycle),
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


class EconomicLearningLedger:
    """Durable, idempotent storage for forecast -> result -> learning -> strategy cycles."""

    PREFIX = "economic-learning:"

    def __init__(self, store: DurableStore) -> None:
        self.store = store

    @classmethod
    def key_for(cls, cycle: EconomicLearningCycle) -> str:
        return cls.PREFIX + cycle.forecast_id

    @staticmethod
    def fingerprint(cycle: EconomicLearningCycle) -> str:
        return hashlib.sha256(_canonical_cycle(cycle).encode("utf-8")).hexdigest()

    def record(self, cycle: EconomicLearningCycle) -> EconomicLearningCycle:
        key = self.key_for(cycle)
        fingerprint = self.fingerprint(cycle)
        result = json.loads(_canonical_cycle(cycle))
        stored = self.store.put_idempotent(key, result, fingerprint)
        if stored != result:
            raise ValueError("Le cycle d'apprentissage réutilise une identité avec un contenu différent.")
        return cycle

    def get(self, forecast_id: str) -> EconomicLearningCycle | None:
        key = self.PREFIX + forecast_id
        stored = self.store.get_idempotent(key)
        if stored is None:
            return None
        encoded = json.dumps(stored, sort_keys=True, separators=(",", ":"))
        expected = self.store.get_idempotency_fingerprint(key)
        actual = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        if expected != actual:
            raise RuntimeError("L'intégrité du cycle d'apprentissage durable est compromise.")
        raise NotImplementedError("Cycle restoration requires explicit domain deserializers.")
