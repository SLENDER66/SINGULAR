from singular.audit import AuditTrail


def test_audit_chain_is_valid_for_ordered_events():
    trail = AuditTrail()
    trail.record("mission", "SYSTEM", "CREATED", {"mission_id": "M1"})
    trail.record("execution", "SYSTEM", "RUNNING", {"mission_id": "M1", "execution_key": "E1"})
    trail.record("execution", "SYSTEM", "COMPLETED", {"mission_id": "M1", "execution_key": "E1"})

    assert AuditTrail.verify_chain(trail.export()) is True


def test_audit_chain_detects_reordering():
    trail = AuditTrail()
    trail.record("one", "SYSTEM", "OK", {"value": 1})
    trail.record("two", "SYSTEM", "OK", {"value": 2})
    trail.record("three", "SYSTEM", "OK", {"value": 3})
    events = trail.export()
    events[1], events[2] = events[2], events[1]

    assert AuditTrail.verify_chain(events) is False


def test_audit_chain_detects_deletion():
    trail = AuditTrail()
    trail.record("one", "SYSTEM", "OK", {"value": 1})
    trail.record("two", "SYSTEM", "OK", {"value": 2})
    trail.record("three", "SYSTEM", "OK", {"value": 3})
    events = trail.export()
    del events[1]

    assert AuditTrail.verify_chain(events) is False


def test_audit_chain_detects_chain_metadata_tampering():
    trail = AuditTrail()
    trail.record("one", "SYSTEM", "OK", {"value": 1})
    trail.record("two", "SYSTEM", "OK", {"value": 2})
    events = trail.export()
    events[1]["payload"]["audit_prev_fingerprint"] = "tampered"

    assert AuditTrail.verify_chain(events) is False


def test_legacy_event_verification_remains_backward_compatible():
    event = {
        "id": "AUD-test",
        "event_type": "execution",
        "actor": "TEST",
        "outcome": "COMPLETED",
        "payload": {"mission_id": "M1", "audit_fingerprint": ""},
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    assert AuditTrail.verify_chain([event]) is False
