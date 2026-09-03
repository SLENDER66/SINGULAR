import pytest

from singular.audit import AuditTrail
from singular.durable import DurableStore


def test_durable_audit_preserves_and_verifies_chain(tmp_path) -> None:
    db = tmp_path / "singular.db"
    store = DurableStore(db)
    trail = AuditTrail()

    first = trail.record("DECISION", "commander", "PROPOSED", {"decision_id": "d1"})
    second = trail.record("RESULT", "executor", "SUCCEEDED", {"decision_id": "d1", "action_id": "a1"})
    store.record_audit(first)
    store.record_audit(second)

    restored = DurableStore(db)
    assert restored.verify_audit_integrity() is True
    assert tuple(event["id"] for event in restored.audit_events()) == (first.id, second.id)


def test_durable_audit_rejects_gap_or_wrong_predecessor(tmp_path) -> None:
    db = tmp_path / "singular.db"
    store = DurableStore(db)
    trail = AuditTrail()
    first = trail.record("DECISION", "commander", "PROPOSED", {"decision_id": "d1"})
    second = trail.record("RESULT", "executor", "SUCCEEDED", {"decision_id": "d1"})
    store.record_audit(first)

    with pytest.raises(ValueError, match="tête de la chaîne"):
        payload = dict(second.payload)
        payload["audit_sequence"] = 3
        invalid = type(second)(second.event_type, second.actor, second.outcome, payload, second.timestamp, second.id)
        store.record_audit(invalid)

    assert store.verify_audit_integrity() is True
