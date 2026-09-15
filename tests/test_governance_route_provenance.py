"""Routing a governance verdict must leave a durable trace.

DurableMissionRuntime.route() only audited its own pre-checks (unknown mission,
contract mismatch) and governance drift. The verdict itself -- the thing that
lets an action cross the execution boundary, or refuses it -- was recorded by
GovernedExecutor into an in-memory AuditTrail that is never persisted and dies
with the process. So after a restart nothing could answer "why was this action
allowed to execute?", and a red-team BLOCK left no durable evidence at all.
"""
import ast
import inspect
import json
import textwrap
from pathlib import Path

import pytest

from singular.autopilot import ActionRequest, Autonomy
from singular.durable import DurableStore, MissionStatus
from singular.mission_runtime import DurableMissionRuntime


def _runtime(tmp_path: Path) -> DurableMissionRuntime:
    return DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))


def _events(runtime: DurableMissionRuntime, event_type: str) -> list[dict]:
    return [event for event in runtime.store.audit_events() if event["event_type"] == event_type]


def test_normal_route_persists_the_governance_verdict(tmp_path: Path):
    runtime = _runtime(tmp_path)
    contract = runtime.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)

    governed = runtime.route(action, contract.mission_id)

    recorded = _events(runtime, "governance_route")
    assert len(recorded) == 1
    payload = recorded[0]["payload"]
    assert recorded[0]["actor"] == "GOVERNOR"
    assert recorded[0]["outcome"] == governed.governor.mode.value
    assert payload["action_id"] == action.id
    assert payload["mission_id"] == contract.mission_id
    assert payload["approval_id"] == governed.governor.approval_id
    assert payload["policy_tier"] == governed.policy_tier
    assert payload["can_prepare"] == governed.can_prepare
    assert payload["can_execute"] == governed.can_execute
    assert payload["requires_human"] == governed.requires_human
    assert payload["reasons"] == list(governed.reasons)
    assert runtime.store.verify_audit_integrity() is True


def test_verdict_is_bound_to_the_action_identity_it_was_issued_for(tmp_path: Path):
    """A verdict without the action fingerprint proves nothing about what was allowed."""
    runtime = _runtime(tmp_path)
    contract = runtime.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)

    governed = runtime.route(action, contract.mission_id)

    payload = _events(runtime, "governance_route")[0]["payload"]
    expected = runtime.approval_integrity.action_fingerprint(governed.action, contract.mission_id)
    assert payload["action_fingerprint"] == expected
    assert payload["idempotency_key"] == runtime.store.idempotency_key("route", contract.mission_id, action.id)


def test_blocked_verdict_is_durably_audited(tmp_path: Path):
    """A refusal is evidence too: BLOCK used to be persisted nowhere."""
    runtime = _runtime(tmp_path)
    contract = runtime.create_mission("finance", "safe plan", autonomy=Autonomy.EXECUTE_AUTHORIZED)

    blocked = runtime.route(ActionRequest("high_risk", "danger", 8, 8, 6), contract.mission_id)

    assert blocked.governor.mode == Autonomy.BLOCK
    recorded = _events(runtime, "governance_route")
    assert [event["outcome"] for event in recorded] == [Autonomy.BLOCK.value]
    assert recorded[0]["payload"]["can_execute"] is False
    assert recorded[0]["payload"]["reasons"] == list(blocked.reasons)
    assert runtime.state(contract.mission_id).status == MissionStatus.BLOCKED


def test_replayed_verdict_is_audited_as_a_replay_after_restart(tmp_path: Path):
    """The decision an execution actually replays must be traceable, not only its first issuance."""
    first = _runtime(tmp_path)
    contract = first.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)
    issued = first.route(action, contract.mission_id)

    restarted = _runtime(tmp_path)
    replayed = restarted.route(action, contract.mission_id)

    assert replayed == issued
    assert len(_events(restarted, "governance_route")) == 1
    replays = _events(restarted, "governance_route_replayed")
    assert len(replays) == 1
    assert replays[0]["outcome"] == issued.governor.mode.value
    assert replays[0]["payload"]["action_fingerprint"] == _events(restarted, "governance_route")[0]["payload"]["action_fingerprint"]
    assert replays[0]["payload"]["can_execute"] == issued.can_execute
    assert restarted.store.verify_audit_integrity() is True


def test_provenance_survives_a_crash_between_decision_and_audit(tmp_path: Path):
    """A verdict persisted without its audit event is re-audited on first replay."""
    crashed = _runtime(tmp_path)
    contract = crashed.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)
    crashed._audit_governance = lambda *args, **kwargs: None  # crash after put_idempotent
    crashed.route(action, contract.mission_id)
    assert _events(crashed, "governance_route") == []

    restarted = _runtime(tmp_path)
    replayed = restarted.route(action, contract.mission_id)

    replays = _events(restarted, "governance_route_replayed")
    assert len(replays) == 1
    assert replays[0]["payload"]["action_fingerprint"] == restarted.approval_integrity.action_fingerprint(replayed.action, contract.mission_id)
    assert restarted.store.verify_audit_integrity() is True


def test_audited_verdicts_keep_one_unbroken_chain_across_missions(tmp_path: Path):
    runtime = _runtime(tmp_path)
    for index in range(3):
        contract = runtime.create_mission(f"career {index}", "prepared", autonomy=Autonomy.PREPARE)
        runtime.route(ActionRequest("send_application", f"send {index}", 5, 6, 6), contract.mission_id)

    persisted = runtime.store.audit_events()
    assert [event["payload"]["audit_sequence"] for event in persisted] == list(range(1, len(persisted) + 1))
    assert len(_events(runtime, "governance_route")) == 3
    assert runtime.store.verify_audit_integrity() is True


def test_governance_drift_still_fails_closed_without_recording_a_verdict(tmp_path: Path):
    """A refused replay must not leave an audit event claiming the decision was served."""
    runtime = _runtime(tmp_path)
    contract = runtime.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)
    runtime.route(action, contract.mission_id)
    key = runtime.store.idempotency_key("route", contract.mission_id, action.id)
    drifted = dict(runtime.store.get_idempotent(key))
    drifted["can_execute"] = not drifted["can_execute"]
    with runtime.store._connect() as conn:
        conn.execute("UPDATE idempotency SET result=? WHERE key=?", (json.dumps(drifted, sort_keys=True), key))

    with pytest.raises(PermissionError, match="politique de gouvernance"):
        runtime.route(action, contract.mission_id)

    assert _events(runtime, "governance_route_replayed") == []
    assert len(_events(runtime, "governance_drift")) == 1


# `_governance_matches` compare six dimensions du verdict persiste a celui que la
# gouvernance rendrait aujourd'hui. C'est le garde anti-politique-perimee : un
# verdict favorable enregistre hier ne doit pas etre reservi si la politique a
# change depuis. Six dimensions, six facons de rejouer une autorisation morte.
#
# Le test ci-dessus n'en essayait qu'une, `can_execute`. Les cinq autres ont ete
# mesurees : neutralisees une a une, la suite entiere restait verte. Une seule
# comparaison qui disparait, et toute une classe de derive redevient rejouable
# sans que rien ne rougisse.
#
# Ce n'est pas la meme famille que les refus qui relisent la decision :
# `verify()` reconstruit ce que la decision porte, donc un refus qui relit un
# champ de la decision est une assurance. Celui-ci compare la decision a l'etat
# **d'aujourd'hui**, et rien d'autre ne le fait a sa place.


#: Les six dimensions de derive, ecrites a la main -- et c'est voulu. La
#: parametrisation ne doit pas se deduire du code qu'elle mesure : un garde
#: neutralise ferait alors disparaitre son propre cas de test, et la mesure
#: dirait « vert » en ne mesurant plus rien. La liste litterale reste, et
#: `test_les_six_dimensions_sont_toutes_couvertes` la confronte au code.
DIMENSIONS_DE_DERIVE = ("policy_tier", "mode", "reasons", "can_prepare", "can_execute", "requires_human")


def _champs_compares() -> tuple[str, ...]:
    """Les clefs du verdict persiste que `_governance_matches` relit vraiment.

    Lues dans le code, pour que la liste ci-dessus ne puisse pas vieillir en
    silence : une septieme comparaison ajoutee sans son cas de derive fait rougir
    `test_les_six_dimensions_sont_toutes_couvertes`, au lieu d'ajouter une
    dimension rejouable que personne n'essaie.

    Seul le premier `cached.get(...)` de chaque comparaison compte : les `get`
    imbriques (`cached.get("can_prepare", cached.get("allowed", False))`) sont des
    valeurs de repli pour un ancien format de cache, pas des dimensions de derive.
    """
    source = textwrap.dedent(inspect.getsource(DurableMissionRuntime._governance_matches))
    retour = next(noeud for noeud in ast.walk(ast.parse(source)) if isinstance(noeud, ast.Return))
    assert isinstance(retour.value, ast.BoolOp), "le garde doit rester une conjonction de comparaisons"

    champs = []
    for comparaison in retour.value.values:
        lus = [noeud.args[0].value for noeud in ast.walk(comparaison)
               if isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute)
               and noeud.func.attr == "get" and noeud.args
               and isinstance(noeud.args[0], ast.Constant)]
        assert lus, f"comparaison qui ne relit pas le verdict persiste : {ast.unparse(comparaison)}"
        champs.append(lus[0])
    return tuple(champs)


def _derive(nom: str, valeur):
    """Une valeur differente de celle enregistree, du meme genre."""
    if isinstance(valeur, bool):
        return not valeur
    if isinstance(valeur, list):
        return [*valeur, "raison apparue apres coup"]
    if nom == "mode":
        return next(mode.value for mode in Autonomy if mode.value != valeur)
    return valeur + "_DERIVE"


def test_les_six_dimensions_sont_toutes_couvertes():
    """Le garde compare exactement ce que le test parametre ci-dessous essaie."""
    assert set(_champs_compares()) == set(DIMENSIONS_DE_DERIVE)


@pytest.mark.parametrize("champ", DIMENSIONS_DE_DERIVE)
def test_chaque_dimension_de_derive_refuse_le_rejeu(tmp_path: Path, champ: str):
    """Une seule dimension derive, et le rejeu doit echouer -- pour chacune des six.

    La derive est ecrite dans la ligne d'idempotence, pas dans la politique : c'est
    le meme modele de menace que le test ci-dessus, celui d'un verdict persiste
    altere. Le refus ne doit dependre d'aucune autre dimension, donc une seule
    bouge a la fois.
    """
    runtime = _runtime(tmp_path)
    contract = runtime.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)
    runtime.route(action, contract.mission_id)

    key = runtime.store.idempotency_key("route", contract.mission_id, action.id)
    enregistre = dict(runtime.store.get_idempotent(key))
    assert champ in enregistre, f"{champ} est compare mais n'est pas persiste"
    altere = dict(enregistre)
    altere[champ] = _derive(champ, enregistre[champ])
    assert altere[champ] != enregistre[champ], "le cas ne derive de rien"
    with runtime.store._connect() as conn:
        conn.execute("UPDATE idempotency SET result=? WHERE key=?",
                     (json.dumps(altere, sort_keys=True), key))

    with pytest.raises(PermissionError, match="politique de gouvernance"):
        runtime.route(action, contract.mission_id)

    assert _events(runtime, "governance_route_replayed") == []
    assert len(_events(runtime, "governance_drift")) == 1
