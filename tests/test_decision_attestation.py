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
    # Shift the validity window forward, not backward: issued_at in the future
    # makes the decision itself invalid ('not active yet') and the store would
    # never reach the fingerprint comparison this test is about.
    altered = recreate(decision, expires_at=decision.expires_at + 1.0)
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


# --- ce que le registre refuse sans rien lever --------------------------------
#
# `verify` et `verify_issuance` refusent en rendant `False`, jamais en levant.
# `tools/gardes_sans_test.py` a rendu chacun de ces refus vrai, un par un : les
# suivants passaient la suite entiere. Un refus qu'aucun test n'atteint est un
# refus qu'on peut retirer par megarde, et celui-la echouerait en silence -- le
# registre repondrait « attestee » et personne ne leverait la main.


@pytest.mark.parametrize("objet", [None, object(), "DEC-DEMO", 42, {"decision_id": "DEC-DEMO"}])
def test_seule_une_decision_se_verifie_contre_le_registre(tmp_path, objet):
    """Le garde de type des deux verifications, qui n'avait aucun temoin.

    La frontiere verifie le type avant d'appeler, donc elle ne peut pas y
    arriver -- mais `ValidatedDecisionService.is_attested` et `OutcomeLedger`
    interrogent le registre directement, et un registre qui dit oui a n'importe
    quoi n'est plus un registre.
    """
    store = DecisionAttestationStore(tmp_path / "attestations.db")

    assert store.verify(objet) is False
    assert store.verify_issuance(objet) is False


def test_une_decision_alteree_apres_son_emission_ne_se_verifie_plus(tmp_path):
    """Mutation apres validation, sur le chemin qui nourrit l'apprentissage.

    `verify_issuance` sert au grand livre des resultats : il autorise
    l'enregistrement de ce qui est arrive pour une decision, meme apres son
    expiration. Si une decision dont le contenu a bouge passait, un resultat
    s'attacherait a une decision qui n'a jamais existe sous cette forme, et la
    calibration apprendrait d'un fait faux.
    """
    decision = _build_decision()
    store = DecisionAttestationStore(tmp_path / "attestations.db")
    store.issue(decision)
    assert store.verify_issuance(decision) is True

    object.__setattr__(decision, "expires_at", decision.expires_at + 1.0)

    assert decision.verify(now=decision.issued_at) is False
    assert store.verify_issuance(decision) is False
    assert store.verify(decision) is False


def test_une_decision_qui_leve_au_lieu_de_repondre_est_refusee(tmp_path):
    """Le refus que rien ne pouvait atteindre par la classe elle-meme.

    `ValidatedTrajectoryDecision.verify` rattrape `TypeError` et `ValueError` et
    rend `False` : la classe ne leve pas. Le `try` de `verify_issuance` garde donc
    le cas de l'objet qui ressemble a une decision et se comporte autrement --
    une substitution. On le joue avec un `verify` qui leve.
    """
    decision = _build_decision()
    store = DecisionAttestationStore(tmp_path / "attestations.db")
    store.issue(decision)

    def leve(now=None):
        raise ValueError("je ne repondrai pas")

    object.__setattr__(decision, "verify", leve)

    assert store.verify_issuance(decision) is False
