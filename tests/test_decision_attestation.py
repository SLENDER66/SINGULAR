from dataclasses import replace
from time import time

import pytest

from singular.decision_attestation import DecisionAttestationStore, ValidatedDecisionIssuer
from tests.test_validated_pipeline import _build_decision
from tests.test_validated_trajectory_decision import recreate


def test_attestation_is_durable_and_matches_exact_decision(tmp_path):
    decision = _build_decision()
    path = tmp_path / "attestations.db"
    first_store = DecisionAttestationStore(path)
    issuer = ValidatedDecisionIssuer(first_store, issuer="test-suite")
    attestation = issuer.issue(decision)

    restarted_store = DecisionAttestationStore(path)
    assert attestation.decision_id == decision.decision_id
    assert attestation.context_fingerprint == decision.context_fingerprint
    assert restarted_store.verify(decision)


def test_in_memory_attestation_store_persists_across_connections():
    decision = _build_decision()
    store = DecisionAttestationStore(":memory:")
    store.issue(decision)
    assert store.get(decision.decision_id) is not None
    assert store.verify(decision)
    store.revoke(decision.decision_id)
    assert store.verify(decision) is False


def test_unissued_decision_is_not_executable_by_attestation_registry(tmp_path):
    decision = _build_decision()
    store = DecisionAttestationStore(tmp_path / "attestations.db")
    assert store.verify(decision) is False


def test_different_context_cannot_reuse_same_decision_id(tmp_path):
    decision = _build_decision()
    store = DecisionAttestationStore(tmp_path / "attestations.db")
    store.issue(decision)
    altered = recreate(decision, issued_at=decision.issued_at + 1.0)
    with pytest.raises(ValueError, match="different context fingerprint"):
        store.issue(altered)


def test_reissued_same_decision_is_idempotent_but_reissue_after_revocation_is_forbidden(tmp_path):
    decision = _build_decision()
    store = DecisionAttestationStore(tmp_path / "attestations.db")
    first = store.issue(decision)
    second = store.issue(decision)
    assert first == second
    store.revoke(decision.decision_id)
    assert store.verify(decision) is False
    with pytest.raises(PermissionError, match="revoked"):
        store.issue(decision)


def test_revocation_survives_process_restart(tmp_path):
    decision = _build_decision()
    path = tmp_path / "attestations.db"
    DecisionAttestationStore(path).issue(decision)
    DecisionAttestationStore(path).revoke(decision.decision_id)
    assert DecisionAttestationStore(path).verify(decision) is False


def test_attestation_obeys_decision_ttl(tmp_path):
    decision = _build_decision()
    store = DecisionAttestationStore(tmp_path / "attestations.db")
    issuer = ValidatedDecisionIssuer(store)
    issuer.issue(decision)
    assert store.verify(decision, now=time() + 7200) is False
