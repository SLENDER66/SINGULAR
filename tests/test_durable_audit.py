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
