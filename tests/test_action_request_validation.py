import math

import pytest

from singular.autopilot import ActionRequest


@pytest.mark.parametrize("field", ["impact", "risk", "reversibility"])
def test_action_request_rejects_non_finite_values(field):
    values = {"impact": 1.0, "risk": 1.0, "reversibility": 9.0}
    for value in (math.nan, math.inf, -math.inf):
        values[field] = value
        with pytest.raises(ValueError, match=field):
            ActionRequest("bounded", "bounded action", **values)


def test_action_request_rejects_out_of_range_values():
    with pytest.raises(ValueError, match="between 0 and 10"):
        ActionRequest("bounded", "bounded action", 11, 1, 9)
    with pytest.raises(ValueError, match="between 0 and 10"):
        ActionRequest("bounded", "bounded action", 1, -1, 9)


# --- le contrat, qui ne se verifiait pas du tout --------------------------------
#
# `ActionRequest` se verifie depuis toujours ; `DelegationContract`, juste au-dessus
# dans le meme fichier, n'avait aucun `__post_init__`. Mesure avant correction :
#
#     store.save_mission(DelegationContract("", "", ""))
#     store.get_mission_status("")  ->  MissionStatus.CREATED
#
# Une mission d'identite vide, ecrite dans le magasin durable, sans qu'aucune
# couche ne bronche. Or `mission_id` est la cle de tout ce qui est durable ici :
# l'etat de mission, les approbations, les cles d'idempotence des executions.
#
# Les trois champs etaient bien verifies -- mais dans
# `ValidatedTrajectoryDecision._validate`, donc trois couches plus loin, et
# seulement pour une mission qui va jusqu'a une decision executable. Le magasin,
# lui, acceptait avant.


@pytest.mark.parametrize("champ", ["mission_id", "objective", "expected_result"])
@pytest.mark.parametrize("vide", ["", "   ", "\t\n"])
def test_delegation_contract_refuse_une_identite_vide(champ, vide):
    from singular.autopilot import DelegationContract

    valeurs = {"mission_id": "MIS-1", "objective": "objectif", "expected_result": "résultat"}
    valeurs[champ] = vide
    with pytest.raises(ValueError, match=champ):
        DelegationContract(**valeurs)


def test_le_magasin_ne_peut_plus_ecrire_une_mission_sans_identite(tmp_path):
    """Le defaut mesure, joue de bout en bout : plus aucune porte n'y mene.

    Le refus est au constructeur, donc `save_mission` n'a rien a verifier : on ne
    peut plus lui fabriquer l'argument. C'est ce que « rendre l'erreur impossible »
    veut dire ici -- pas un garde de plus au bord du magasin.
    """
    from singular.autopilot import Autonomy, DelegationContract
    from singular.durable import DurableStore

    store = DurableStore(tmp_path / "singular.db")
    with pytest.raises(ValueError, match="mission_id"):
        store.save_mission(DelegationContract("", "objectif", "résultat",
                                              autonomy=Autonomy.EXECUTE_AUTHORIZED))
    assert store.load_mission("") is None
