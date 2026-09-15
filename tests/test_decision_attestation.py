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


@pytest.mark.parametrize("objet", [None, object(), "DEC-DEMO", 42, {"decision_id": "DEC-DEMO"}])
def test_seule_une_decision_s_atteste(tmp_path, objet):
    """L'emission a le meme garde de type, et lui non plus n'avait rien.

    Sans lui, `decision.verify()` part sur un objet quelconque : `AttributeError`
    au lieu de `ValueError`. Et le registre est ecrit juste apres -- un objet qui
    porterait un `verify()` complaisant et un `decision_id` obtiendrait une
    attestation durable, que la frontiere relirait comme une autorisation.
    """
    store = DecisionAttestationStore(tmp_path / "attestations.db")

    with pytest.raises(ValueError, match="only a valid active decision"):
        store.issue(objet, issuer="test-suite")
    with pytest.raises(ValueError, match="only a valid active decision"):
        ValidatedDecisionIssuer(store, issuer="test-suite").issue(objet)


def test_une_decision_alteree_ne_s_atteste_pas(tmp_path):
    """L'autre moitie du meme garde : une vraie decision, mais dont le contenu a bouge.

    Le type ne suffit pas -- c'est `verify()` qui refait l'empreinte sur les
    champs presents. Une decision alteree apres sa construction est du bon type et
    ne se verifie plus ; sans cette moitie, elle obtiendrait une attestation
    durable, et la frontiere relit l'attestation comme une autorisation. Mutation
    apres validation, du cote de l'emission cette fois.
    """
    decision = _build_decision()
    store = DecisionAttestationStore(tmp_path / "attestations.db")

    object.__setattr__(decision, "expires_at", decision.expires_at + 1.0)
    assert decision.verify() is False

    with pytest.raises(ValueError, match="only a valid active decision"):
        store.issue(decision, issuer="test-suite")
    assert store.get(decision.decision_id) is None


# Le refus suivant de `issue` -- « cannot attest an inactive decision », la fenetre
# lue a l'instant de l'emission -- n'a pas de temoin et n'en aura pas : ses deux
# moities sont inatteignables. `verify()` juste au-dessus appelle `_validate(now)`,
# qui refuse deja une decision pas encore active ou expiree. Mesure, pas deduit :
# une decision dont la fenetre est fermee ressort avec « only a valid active
# decision can be attested », le message de la ligne d'avant. C'est une assurance
# derriere un controle qui la precede -- la deuxieme des trois familles.


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


# --- une ligne d'attestation abimee -------------------------------------------
#
# Les trois champs d'identite d'une attestation sont verifies a la construction,
# et `_row` construit l'objet depuis la base : une ligne dont une identite a ete
# videe doit donc etre refusee a la relecture, pas rendue vide. La mutation par
# moities a nomme ce refus -- ses trois moities dans une seule ligne, et aucune
# n'etait essayee.
#
# L'espace au lieu de la chaine vide n'est pas un detail : c'est ce qui distingue
# `not champ` de `not champ.strip()`. Une identite faite d'un espace est un nom
# que rien ne porte.

@pytest.mark.parametrize("champ", ["decision_id", "context_fingerprint", "issuer"])
def test_une_identite_videe_dans_la_base_est_refusee_a_la_relecture(tmp_path, champ):
    decision = _build_decision()
    store = DecisionAttestationStore(tmp_path / "attestations.db")
    ValidatedDecisionIssuer(store, issuer="test-suite").issue(decision)

    with store._connect() as conn:
        conn.execute(
            f"UPDATE decision_attestations SET {champ}=' ' WHERE decision_id=?",
            (decision.decision_id,),
        )
    # Vider `decision_id` deplace la clef : on relit la ligne la ou elle est.
    clef = " " if champ == "decision_id" else decision.decision_id

    with pytest.raises(ValueError, match="identity fields are required"):
        store.get(clef)


# --- et son intervalle de validite --------------------------------------------
#
# Meme forme, meme chemin : trois refus dans une ligne, aucun essaye. Une
# attestation dont la fenetre de validite n'est pas un intervalle fini n'a pas de
# sens -- `now < expires_at` est faux pour tout `now` si `expires_at` est NaN, et
# vrai pour tout `now` si c'est l'infini. Le premier est fail-closed par accident,
# le second est un jeton eternel.

@pytest.mark.parametrize("champ, valeur", [
    ("issued_at", "inf"),
    ("issued_at", "nan"),
    ("expires_at", "inf"),
    ("expires_at", "nan"),
])
def test_une_attestation_dont_la_fenetre_n_est_pas_finie_est_refusee(tmp_path, champ, valeur):
    decision = _build_decision()
    store = DecisionAttestationStore(tmp_path / "attestations.db")
    ValidatedDecisionIssuer(store, issuer="test-suite").issue(decision)

    with store._connect() as conn:
        conn.execute(
            f"UPDATE decision_attestations SET {champ}=? WHERE decision_id=?",
            (valeur, decision.decision_id),
        )

    with pytest.raises(ValueError, match="validity interval is invalid"):
        store.get(decision.decision_id)


def test_une_attestation_qui_expire_avant_d_etre_emise_est_refusee(tmp_path):
    """Une fenetre nulle ou negative n'est pas une fenetre : elle autorise zero instant."""
    decision = _build_decision()
    store = DecisionAttestationStore(tmp_path / "attestations.db")
    attestation = ValidatedDecisionIssuer(store, issuer="test-suite").issue(decision)

    with store._connect() as conn:
        conn.execute("UPDATE decision_attestations SET expires_at=? WHERE decision_id=?",
                     (attestation.issued_at, decision.decision_id))

    with pytest.raises(ValueError, match="validity interval is invalid"):
        store.get(decision.decision_id)


def test_une_attestation_ne_vaut_pas_pour_une_autre_decision_du_meme_identifiant(tmp_path):
    """Le cote lecture de la liaison, que le cote ecriture laissait croire couvert.

    `test_different_context_cannot_reuse_same_decision_id` tient l'ecriture :
    `issue` refuse une seconde decision qui porterait le meme identifiant avec
    une autre empreinte. Personne ne tenait la lecture -- `verify` --, et c'est
    elle que la frontiere appelle avant d'executer.

    `tools/gardes_sans_test.py` a nomme les deux premieres moities du `and` qui
    la compose. Celle-ci est la liaison elle-meme : sans elle, une attestation
    emise pour une decision validerait n'importe quelle autre decision portant
    le meme identifiant. C'est precisement ce que l'attestation existe pour
    empecher.

    La seconde decision partage l'identifiant **et la fenetre de validite** de la
    premiere : sans ca, ce sont les comparaisons de dates qui refuseraient, et
    la liaison d'empreinte resterait sans temoin.
    """
    from tests.test_validated_trajectory_decision import recreate

    attestee = _build_decision()
    store = DecisionAttestationStore(tmp_path / "attestations.db")
    store.issue(attestee)

    autre = recreate(attestee, calibration={**dict(attestee.calibration), "sonde": 0.5})
    assert autre.decision_id == attestee.decision_id
    assert (autre.issued_at, autre.expires_at) == (attestee.issued_at, attestee.expires_at)
    assert autre.context_fingerprint != attestee.context_fingerprint
    assert autre.verify() is True, "elle doit etre valide en elle-meme, sinon on teste autre chose"

    assert store.verify(autre) is False
    assert store.verify_issuance(autre) is False, (
        "le grand livre des resultats lit la meme liaison, et il la lisait sans temoin")
    assert store.verify(attestee) is True
    assert store.verify_issuance(attestee) is True


def test_une_attestation_sans_emetteur_est_refusee(tmp_path):
    """Qui a emis compte, sinon la provenance de l'autorisation n'a pas de nom.

    Les deux refus -- celui du magasin a l'emission et celui de l'emetteur a sa
    construction -- n'avaient aucun temoin. Le second garde la porte d'entree :
    un `ValidatedDecisionIssuer` sans nom emettrait des attestations anonymes.
    """
    from singular.decision_attestation import ValidatedDecisionIssuer

    decision = _build_decision()
    store = DecisionAttestationStore(tmp_path / "attestations.db")

    with pytest.raises(ValueError, match="issuer is required"):
        store.issue(decision, issuer="   ")

    with pytest.raises(ValueError, match="issuer is required"):
        ValidatedDecisionIssuer(store, issuer=" ")


def test_un_statut_d_attestation_inconnu_est_refuse():
    """Une ligne venue du disque ne dicte pas ce qu'un statut veut dire.

    Le refus vit dans `__post_init__`, donc il garde aussi bien un objet
    fabrique qu'une ligne relue d'une base ecrite par une autre version.
    """
    from singular.decision_attestation import DecisionAttestation

    with pytest.raises(ValueError, match="status is invalid"):
        DecisionAttestation("DEC-1", "empreinte", 0.0, 10.0, "PEUT-ETRE", "singular", "2026-01-01")


def test_une_attestation_dont_la_fenetre_a_ete_elargie_ne_verifie_plus(tmp_path):
    """Elargir n'est pas casser, et c'est pour ca que personne ne l'essayait.

    Le test voisin ecrase `expires_at` par une valeur qui rend la fenetre nulle :
    `__post_init__` la refuse avant meme qu'on compare quoi que ce soit. Deplacer
    `issued_at` **en arriere** laisse une fenetre parfaitement valide -- plus
    large, simplement -- donc la ligne se relit sans broncher et il ne reste que
    la comparaison avec la decision pour s'y opposer.

    C'est la moitie que `tools/gardes_sans_test.py` a nommee. Elle n'est pas
    couverte par l'empreinte : l'attestation est une ligne persistee **a part**,
    et ses dates peuvent bouger sans que la decision change d'un octet.
    """
    decision = _build_decision()
    store = DecisionAttestationStore(tmp_path / "attestations.db")
    attestation = ValidatedDecisionIssuer(store, issuer="test-suite").issue(decision)
    assert store.verify(decision) is True

    with store._connect() as conn:
        conn.execute("UPDATE decision_attestations SET issued_at=? WHERE decision_id=?",
                     (attestation.issued_at - 3600.0, decision.decision_id))

    relue = store.get(decision.decision_id)
    assert relue.expires_at > relue.issued_at, "la fenetre reste valide : c'est le sujet"
    assert store.verify(decision) is False
    # `verify_issuance` porte la meme comparaison, et il sert au grand livre des
    # resultats -- celui qui relie prediction et realite, donc qui nourrit la
    # calibration. Il ignore l'expiration et la revocation expres ; il ne doit
    # pas pour autant accepter une attestation dont les dates ont bouge.
    assert store.verify_issuance(decision) is False


def test_une_attestation_prolongee_par_la_fin_ne_verifie_plus(tmp_path):
    """Le bord symetrique, et il manquait aussi.

    Reculer `issued_at` elargit la fenetre par le debut ; avancer `expires_at`
    l'elargit par la fin, et c'est le bord qui **prolonge** une autorisation.
    Les deux laissent une fenetre valide, donc `__post_init__` n'a rien a dire :
    seule la comparaison avec la decision s'y oppose.

    J'avais suppose cette moitie couverte par le test qui ecrase `expires_at`.
    Elle ne l'etait pas : ce test-la rend la fenetre nulle, ce qui tombe bien
    avant, sur un autre garde. Supposer qu'un champ est couvert parce qu'un test
    le nomme est exactement l'erreur que l'audit de mutation existe pour rendre
    visible.
    """
    decision = _build_decision()
    store = DecisionAttestationStore(tmp_path / "attestations.db")
    attestation = ValidatedDecisionIssuer(store, issuer="test-suite").issue(decision)
    assert store.verify(decision) is True

    with store._connect() as conn:
        conn.execute("UPDATE decision_attestations SET expires_at=? WHERE decision_id=?",
                     (attestation.expires_at + 3600.0, decision.decision_id))

    relue = store.get(decision.decision_id)
    assert relue.expires_at > relue.issued_at, "la fenetre reste valide : c'est le sujet"
    assert store.verify(decision) is False
    assert store.verify_issuance(decision) is False


# --- ce que la revocation doit refuser ----------------------------------------

@pytest.mark.parametrize("cas", ["jamais_emise", "deja_revoquee"])
def test_revoquer_ce_qui_n_est_pas_revocable_leve(tmp_path, cas):
    """`rowcount` est la **seule** façon de savoir si la révocation a eu lieu.

    L'`UPDATE` vise `decision_id AND status='ISSUED'` et il n'y a aucun `SELECT`
    avant lui : contrairement aux gardes de `rowcount` du journal, celui-ci n'est
    pas une assurance derrière un verrou, c'est le contrôle lui-même. Zéro ligne
    touchée veut dire « il n'y avait rien à révoquer », et l'appelant doit
    l'apprendre — sinon il croit avoir révoqué et continue.

    Deux façons d'avoir zéro ligne, et aucune n'était essayée : l'attestation
    n'a jamais été émise, ou elle l'a déjà été et révoquée. Les tests voisins ne
    révoquent que ce qui existe, une seule fois.
    """
    decision = _build_decision()
    store = DecisionAttestationStore(tmp_path / "attestations.db")

    if cas == "deja_revoquee":
        store.issue(decision)
        store.revoke(decision.decision_id)
        assert store.verify(decision) is False, "le premier retrait doit avoir compté"

    with pytest.raises(KeyError):
        store.revoke(decision.decision_id)


def test_revoquer_une_autre_decision_ne_touche_pas_la_bonne(tmp_path):
    """Sans ça, le test ci-dessus passerait avec une révocation qui rate tout.

    Ce qui est visé est « rien à révoquer », pas « la révocation ne marche
    jamais ». Une attestation émise à côté doit rester valide.
    """
    gardee = _build_decision()
    store = DecisionAttestationStore(tmp_path / "attestations.db")
    store.issue(gardee)

    with pytest.raises(KeyError):
        store.revoke("DEC-QUI-N-EXISTE-PAS")

    assert store.verify(gardee) is True, "la révocation ratée a touché une autre ligne"


# --- la fenetre de validite, entre la verification et l'emission ---------------

@pytest.mark.parametrize("quand", ["pas_encore_active", "deja_expiree"])
def test_une_decision_qui_sort_de_sa_fenetre_entre_les_deux_controles_est_refusee(
        tmp_path, monkeypatch, quand):
    """Le second contrôle de la fenêtre, et ce qu'il défend est une course.

    `issue()` commence par `decision.verify()`, qui refuse déjà une décision
    inactive — `_validate` lève « not active yet » et « has expired ». Le contrôle
    qui suit, `now < issued_at or now >= expires_at`, ne peut donc jamais se
    déclencher sur la même horloge : les deux moitiés survivaient à toute
    mutation, et ça ressemblait à un garde décoratif.

    Ce n'en est pas un. Les deux lectures de l'horloge sont **distinctes** :
    `verify()` prend la sienne, `issue()` prend la sienne juste après. Une
    décision qui expire entre les deux passe la première et doit échouer à la
    seconde. C'est un TOCTOU d'une poignée de microsecondes, et c'est exactement
    ce que la section 7 du mandat demande de chercher.

    Le test le rend constructible en figeant la seconde lecture, sans toucher à
    la première : la décision est vraiment valide quand `verify()` la regarde.
    """
    from singular import decision_attestation as module

    decision = _build_decision()
    store = DecisionAttestationStore(tmp_path / "attestations.db")
    assert decision.verify() is True, "la décision doit être valide au premier regard"

    dehors = (decision.issued_at - 1.0 if quand == "pas_encore_active"
              else decision.expires_at + 1.0)
    monkeypatch.setattr(module, "time", lambda: dehors)

    with pytest.raises(ValueError, match="inactive"):
        store.issue(decision)

    monkeypatch.undo()
    assert store.get(decision.decision_id) is None, (
        "rien ne doit avoir été écrit pour une décision hors de sa fenêtre")


# --- l'invariant du dataclass, et ce qui s'appuie dessus -----------------------

@pytest.mark.parametrize("champ, valeur, motif", [
    ("status", "PEUT-ETRE", "status is invalid"),
    ("status", "", "status is invalid"),
    ("decision_id", "   ", "identity fields are required"),
    ("context_fingerprint", "", "identity fields are required"),
    ("issuer", " ", "identity fields are required"),
    ("expires_at", 0.0, "validity interval is invalid"),
    ("issued_at", float("nan"), "validity interval is invalid"),
])
def test_une_attestation_mal_formee_ne_se_construit_pas(champ, valeur, motif):
    """L'invariant sur lequel `verify_issuance` s'appuie sans le redire.

    `verify_issuance` finit par `attestation.status in {"ISSUED", "REVOKED"}`.
    Cette moitié-là ne peut jamais décider, parce qu'aucune attestation ne se
    construit avec un autre statut — mais c'était une promesse que rien ne
    tenait : `__post_init__` n'avait aucun témoin, donc l'assurance s'appuyait
    sur du vide.

    Le mandat dit de refuser plutôt que d'autoriser en cas d'ambiguïté. Une
    attestation est ce qui autorise une exécution à franchir la frontière : elle
    n'existe pas à moitié.
    """
    from singular.decision_attestation import DecisionAttestation

    valide = {
        "decision_id": "DEC-1", "context_fingerprint": "abc", "issued_at": 1000.0,
        "expires_at": 2000.0, "status": "ISSUED", "issuer": "test",
        "created_at": "2026-09-15T00:00:00+00:00",
    }
    assert DecisionAttestation(**valide).status == "ISSUED", "le cas nominal doit tenir"

    with pytest.raises(ValueError, match=motif):
        DecisionAttestation(**(valide | {champ: valeur}))
