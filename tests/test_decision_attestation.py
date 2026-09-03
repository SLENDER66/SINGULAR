from dataclasses import replace
from time import time

import pytest

from singular.decision_attestation import DecisionAttestationStore, ValidatedDecisionIssuer
from tests.test_validated_pipeline import _build_decision


def test_attestation_is_durable_and_matches_exact_decision():
    decision = _build_decision()
    store = DecisionAttestationStore(":memory:")
    issuer = ValidatedDecisionIssuer(store, issuer="test-suite")
    attestation = issuer.issue(decision)

    assert attestation.decision_id == decision.decision_id
    assert attestation.context_fingerprint == decision.context_fingerprint
    assert issuer.verify(decision)


def test_unissued_decision_is_not_executable_by_attestation_registry():
    decision = _build_decision()
    store = DecisionAttestationStore(":memory:")
    assert store.verify(decision) is False


def test_different_context_cannot_reuse_same_decision_id():
    decision = _build_decision()
    store = DecisionAttestationStore(":memory:")
    store.issue(decision)
    forged = replace(decision, decision_id="DEC-OTHER")
    object.__setattr__(forged, "context_fingerprint", decision.context_fingerprint)
    assert store.verify(forged) is False


def test_reissued_same_decision_is_idempotent_but_reissue_after_revocation_is_forbidden():
    decision = _build_decision()
    store = DecisionAttestationStore(":memory:")
    first = store.issue(decision)
    second = store.issue(decision)
    assert first == second
    store.revoke(decision.decision_id)
    assert store.verify(decision) is False
    with pytest.raises(PermissionError, match="revoked"):
        store.issue(decision)


def test_attestation_obeys_decision_ttl():
    decision = _build_decision()
    store = DecisionAttestationStore(":memory:")
    issuer = ValidatedDecisionIssuer(store)
    issuer.issue(decision)
    assert store.verify(decision, now=time() + 7200) is False
