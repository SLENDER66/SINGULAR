import pytest

from singular.autopilot import ApprovalRequest, ApprovalStatus, DelegationContract
from singular.durable import DurableStore


def _store(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract(mission_id="MIS-APP", objective="test", expected_result="done"))
    return store


def test_existing_approval_cannot_be_replaced(tmp_path):
    store = _store(tmp_path)
    original = ApprovalRequest("ACT-1", "approved for execution", ApprovalStatus.PENDING, "APR-1")
    store.save_approval(original, "MIS-APP")

    with pytest.raises(ValueError, match="approbation existante est immuable"):
        store.save_approval(ApprovalRequest("ACT-2", "different", ApprovalStatus.PENDING, "APR-1"), "MIS-OTHER")

    persisted = store.get_approval("APR-1")
    assert persisted.action_id == "ACT-1"
    assert persisted.status is ApprovalStatus.PENDING


def test_terminal_approval_cannot_be_rewritten(tmp_path):
    store = _store(tmp_path)
    store.save_approval(ApprovalRequest("ACT-1", "approved", ApprovalStatus.PENDING, "APR-1"), "MIS-APP")
    store.update_approval("APR-1", ApprovalStatus.APPROVED)

    with pytest.raises(ValueError, match="Transition d'approbation interdite"):
        store.update_approval("APR-1", ApprovalStatus.REJECTED)

    assert store.get_approval("APR-1").status is ApprovalStatus.APPROVED


def test_same_terminal_approval_is_idempotent(tmp_path):
    store = _store(tmp_path)
    store.save_approval(ApprovalRequest("ACT-1", "approved", ApprovalStatus.PENDING, "APR-1"), "MIS-APP")
    store.update_approval("APR-1", ApprovalStatus.APPROVED)

    result = store.update_approval("APR-1", ApprovalStatus.APPROVED)

    assert result.status is ApprovalStatus.APPROVED


# --- deux mains sur la meme approbation -----------------------------------------
#
# `update_approval` lit l'etat, refuse une transition depuis un etat terminal, puis
# ecrit **sous condition** que l'approbation soit encore PENDING. Si un autre a
# tranche entre les deux, l'ecriture ne touche aucune ligne et le refus dit
# « concurrence d'etat ». Ce refus n'avait aucun temoin.
#
# Le cas est reel et c'est le pire de la journee d'un humain : deux onglets, ou le
# clavier apres l'app. Sans ce refus, le second appel se croirait accepte et
# rendrait l'approbation qu'il voulait -- alors que la base porte l'autre verdict.
# Une autorisation humaine qu'on peut doubler n'est plus une autorisation.

class _TrancheApresLaLecture:
    """Un autre acteur tranche l'approbation entre la lecture et l'ecriture."""

    def __init__(self, conn, approval_id: str, vers) -> None:
        self._conn = conn
        self._approval = approval_id
        self._vers = vers
        self._deja = False

    def execute(self, sql, params=()):
        curseur = self._conn.execute(sql, params)
        if not self._deja and sql.lstrip().startswith("SELECT approval_id,action_id,reason,status"):
            self._deja = True
            self._conn.execute(
                "UPDATE approvals SET status=? WHERE approval_id=?",
                (self._vers.value, self._approval),
            )
        return curseur


def test_une_approbation_doublee_par_un_autre_refuse(tmp_path) -> None:
    import pytest

    from singular.autopilot import ApprovalRequest, ApprovalStatus
    from singular.durable import DurableStore

    store = DurableStore(tmp_path / "singular.db")
    store.save_approval(ApprovalRequest("ACT-1", "raison", ApprovalStatus.PENDING, "APR-RACE"))

    # `update_approval` ouvre sa propre connexion : c'est elle qu'on espionne,
    # sinon le magasin ne verrait jamais notre intrus.
    import contextlib

    vraie = store._connect

    @contextlib.contextmanager
    def connexion_espionnee():
        with vraie() as conn:
            yield _TrancheApresLaLecture(conn, "APR-RACE", ApprovalStatus.REJECTED)

    store._connect = connexion_espionnee
    try:
        with pytest.raises(RuntimeError, match="concurrence d'état"):
            store.update_approval("APR-RACE", ApprovalStatus.APPROVED)
    finally:
        store._connect = vraie
    # Ce que le test prouve : **notre** verdict n'a pas ete ecrit. L'intrus, lui,
    # partage notre transaction -- une simulation ne peut pas faire autrement dans
    # un seul processus -- donc le retour arriere efface aussi son ecriture et
    # l'approbation se retrouve PENDING. Dans la vraie course il tient sa propre
    # transaction et son verdict reste ; dans les deux cas, le nôtre ne passe pas.
    assert store.get_approval("APR-RACE").status is not ApprovalStatus.APPROVED
