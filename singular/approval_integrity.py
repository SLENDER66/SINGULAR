from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .autopilot import ActionRequest, DelegationContract


class ApprovalIntegrityStore:
    """Native immutable authorization fields persisted directly on approvals."""

    _COLUMNS = {
        "action_fingerprint": "TEXT",
        "capability_fingerprint": "TEXT",
        "contract_fingerprint": "TEXT",
    }

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(approvals)")}
            for name, sql_type in self._COLUMNS.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE approvals ADD COLUMN {name} {sql_type}")

    @staticmethod
    def _fingerprint(value: Any) -> str:
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @classmethod
    def action_fingerprint(cls, action: ActionRequest, mission_id: str | None) -> str:
        payload = asdict(action)
        payload.pop("id", None)
        return cls._fingerprint({"mission_id": mission_id, "action": payload})

    @classmethod
    def capability_fingerprint(cls, action: ActionRequest) -> str:
        from .capabilities import CapabilityRegistry

        if action.capability is None:
            return cls._fingerprint({"capability": None})
        spec = CapabilityRegistry.resolve(action.capability)
        if spec is None:
            return cls._fingerprint({"capability": "UNKNOWN", "name": action.capability})
        return cls._fingerprint({"capability": asdict(spec)})

    @classmethod
    def contract_fingerprint(cls, contract: DelegationContract | None) -> str:
        return cls._fingerprint({"contract": asdict(contract) if contract is not None else None})

    def bind(self, approval_id: str, action: ActionRequest, mission_id: str | None, contract: DelegationContract | None) -> None:
        values = (self.action_fingerprint(action, mission_id), self.capability_fingerprint(action), self.contract_fingerprint(contract))
        with self._connect() as conn:
            row = conn.execute("SELECT action_fingerprint,capability_fingerprint,contract_fingerprint FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
            if row is None:
                raise KeyError(approval_id)
            existing = tuple(row[name] for name in self._COLUMNS)
            if any(value is not None for value in existing):
                if existing != values:
                    raise ValueError("L'identité immuable de l'approbation ne peut pas être modifiée.")
                return
            conn.execute("UPDATE approvals SET action_fingerprint=?, capability_fingerprint=?, contract_fingerprint=? WHERE approval_id=?", (*values, approval_id))

    def get(self, approval_id: str) -> dict[str, str | None]:
        with self._connect() as conn:
            row = conn.execute("SELECT action_fingerprint,capability_fingerprint,contract_fingerprint FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
        if row is None:
            raise KeyError(approval_id)
        return {name: row[name] for name in self._COLUMNS}

    def validate(self, approval_id: str, action: ActionRequest, mission_id: str | None, contract: DelegationContract | None) -> None:
        stored = self.get(approval_id)
        expected = {
            "action_fingerprint": self.action_fingerprint(action, mission_id),
            "capability_fingerprint": self.capability_fingerprint(action),
            "contract_fingerprint": self.contract_fingerprint(contract),
        }
        if any(stored[name] is None for name in expected):
            raise PermissionError("Approbation sans empreintes natives complètes : exécution refusée.")
        if stored != expected:
            raise PermissionError("L'identité, le contexte ou l'autorité de l'action a changé depuis l'approbation.")
