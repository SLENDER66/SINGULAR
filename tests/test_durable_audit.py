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


# --- ce qu'un evenement doit porter pour entrer dans la chaine durable ----------
#
# `record_audit` exige une sequence positive et des empreintes non vides. Les deux
# refus n'avaient aucun temoin -- nommes par la passe de mutation sur le socle.
#
# Le chemin est reel : `AuditEvent` est une dataclass publique et `record_audit`
# est appele par le runtime. Un module qui enregistrerait un evenement sans passer
# par `AuditTrail` -- donc sans empreinte ni rang -- casserait l'ordre et la chaine
# de l'audit durable, qui est ce qui permet d'expliquer apres coup pourquoi une
# action a franchi la frontiere. Un trou dans la provenance ne se voit pas avant
# qu'on en ait besoin.

@pytest.mark.parametrize("sequence", [None, 0, -1, "1", 1.0, True])
def test_un_evenement_sans_rang_positif_n_entre_pas(tmp_path, sequence) -> None:
    from singular.audit import AuditEvent

    store = DurableStore(tmp_path / "singular.db")
    charge = {"decision_id": "d1", "audit_fingerprint": "a" * 64,
              "audit_chain_fingerprint": "b" * 64}
    if sequence is not None:
        charge["audit_sequence"] = sequence

    with pytest.raises(ValueError, match="séquence positive"):
        store.record_audit(AuditEvent("DECISION", "commander", "PROPOSED", charge))


@pytest.mark.parametrize("champ", ["audit_fingerprint", "audit_chain_fingerprint"])
@pytest.mark.parametrize("valeur", [None, "", 42])
def test_un_evenement_sans_empreinte_n_entre_pas(tmp_path, champ, valeur) -> None:
    from singular.audit import AuditEvent

    store = DurableStore(tmp_path / "singular.db")
    charge = {"decision_id": "d1", "audit_sequence": 1,
              "audit_fingerprint": "a" * 64, "audit_chain_fingerprint": "b" * 64}
    if valeur is None:
        del charge[champ]
    else:
        charge[champ] = valeur

    with pytest.raises(ValueError, match="empreintes valides"):
        store.record_audit(AuditEvent("DECISION", "commander", "PROPOSED", charge))


# --- un evenement forge n'entre pas dans la chaine durable ----------------------
#
# Le dernier refus de `record_audit` verifie deux choses dans la meme ligne :
# l'empreinte de chaine annoncee est bien celle que le magasin recalcule, et
# l'evenement porte une empreinte qui couvre son propre contenu. Aucune des deux
# moities n'avait de temoin.
#
# C'est ce qui empeche d'ecrire dans l'audit durable un evenement fabrique a la
# main : le rang et le precedent peuvent etre justes -- ils sont lisibles -- alors
# que le contenu ou le chainage ne le sont pas. Un audit ou l'on peut inserer ce
# qu'on veut n'explique plus rien.

def test_une_empreinte_de_chaine_fausse_n_entre_pas(tmp_path) -> None:
    from dataclasses import replace

    store = DurableStore(tmp_path / "singular.db")
    trail = AuditTrail()
    event = trail.record("DECISION", "commander", "PROPOSED", {"decision_id": "d1"})
    charge = dict(event.payload)
    charge["audit_chain_fingerprint"] = "0" * 64

    with pytest.raises(ValueError, match="intégrité de l'événement d'audit"):
        store.record_audit(replace(event, payload=charge))
    assert store.audit_events() == ()


def test_un_evenement_dont_le_contenu_a_bouge_n_entre_pas(tmp_path) -> None:
    """L'autre moitie : le chainage est juste, le contenu ne l'est plus.

    L'empreinte propre d'un evenement exclut sa position dans la chaine -- c'est
    voulu, ca permet de le replacer derriere des ecritures qu'il n'avait pas vues.
    Elle couvre donc le reste, et c'est cette moitie-la qui le verifie : changer
    l'acteur en gardant les empreintes laisse le chainage coherent et le contenu
    faux.
    """
    from dataclasses import replace

    store = DurableStore(tmp_path / "singular.db")
    trail = AuditTrail()
    event = trail.record("DECISION", "commander", "PROPOSED", {"decision_id": "d1"})

    with pytest.raises(ValueError, match="intégrité de l'événement d'audit"):
        store.record_audit(replace(event, actor="quelqu-un-d-autre"))
    assert store.audit_events() == ()
