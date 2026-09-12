from __future__ import annotations

import copy

import pytest

from singular.audit import AuditTrail


def test_record_overwrites_caller_supplied_chain_metadata() -> None:
    trail = AuditTrail()
    event = trail.record(
        "security_test",
        "red_team",
        "observed",
        {
            "value": "trusted-content",
            "audit_sequence": 999,
            "audit_fingerprint": "forged",
            "audit_prev_fingerprint": "forged-prev",
            "audit_chain_fingerprint": "forged-chain",
        },
    )

    assert event.payload["audit_sequence"] == 1
    assert event.payload["audit_prev_fingerprint"] == ""
    assert event.payload["audit_fingerprint"] == event.fingerprint
    assert event.payload["audit_chain_fingerprint"] == AuditTrail._chain_fingerprint(
        1, event.fingerprint, ""
    )
    assert AuditTrail.verify_chain(trail.export())


def test_forged_persisted_chain_metadata_is_rejected() -> None:
    trail = AuditTrail()
    trail.record("one", "actor", "ok", {"value": 1})
    trail.record("two", "actor", "ok", {"value": 2})
    persisted = trail.export()

    forged = copy.deepcopy(persisted)
    forged[1]["payload"]["audit_sequence"] = 99
    forged[1]["payload"]["audit_chain_fingerprint"] = AuditTrail._chain_fingerprint(
        99,
        forged[1]["payload"]["audit_fingerprint"],
        forged[1]["payload"]["audit_prev_fingerprint"],
    )

    assert not AuditTrail.verify_chain(forged)
    with pytest.raises(ValueError):
        AuditTrail.restore(forged)


def test_event_content_tampering_is_rejected() -> None:
    trail = AuditTrail()
    trail.record("security_test", "actor", "ok", {"value": "original"})
    forged = trail.export()
    forged[0]["payload"]["value"] = "tampered"

    assert not AuditTrail.verify_chain(forged)
