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


def test_la_plage_seule_refuse_deja_le_non_fini():
    """Pourquoi `not isfinite(value)` reste, alors qu'il ne decide jamais seul.

    La passe de mutation le denonce comme une moitie qui survit : neutralisee, la
    suite entiere reste verte. C'est exact et c'est arithmetique -- toute comparaison
    avec NaN est fausse, et `inf <= 10` l'est aussi, donc `not 0 <= value <= 10`
    refuse deja les trois valeurs non finies.

    Elle reste quand meme, et ce n'est pas un oubli. La section 7 du mandat demande
    de chercher activement NaN et l'infini : un garde qui les nomme dit ce qu'il
    refuse, la ou une plage seule le fait par un effet de bord de la norme IEEE que
    le prochain lecteur devra redecouvrir. Ce test-ci pin l'equivalence pour que
    personne n'ait a la redemontrer -- ni ne l'inverse en croyant simplifier.
    """
    for valeur in (math.nan, math.inf, -math.inf):
        assert not (0 <= valeur <= 10), f"{valeur!r} passerait la plage seule"


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


# --- les quatre champs de texte, que rien n'essayait -----------------------------
#
# Ce fichier ne verifiait que les trois nombres. Les quatre champs de texte d'une
# action n'avaient aucun temoin, et ce ne sont pas des etiquettes : l'identifiant
# relie l'action a son autorisation et a son resultat, le contrat dit quelle
# delegation la couvre, la capacite nommee est lue par la politique, et le jeton
# d'execution designe le code autorise a la faire.


@pytest.mark.parametrize("champ", ["id", "name", "description"])
@pytest.mark.parametrize("vide", ["", "   ", "\t"])
def test_action_request_exige_identifiant_nom_et_description(champ, vide):
    """Les trois moities du meme garde, jouees separement.

    Une action sans identifiant ne peut etre rapprochee ni de l'autorisation qui la
    couvre ni du resultat qu'elle produit -- et le gouverneur, la politique et le
    rapport global la nomment tous par cet identifiant.
    """
    valeurs = {"name": "bounded", "description": "bounded action", "impact": 1.0,
               "risk": 1.0, "reversibility": 9.0}
    if champ == "id":
        valeurs["id"] = vide
    else:
        valeurs[champ] = vide
    with pytest.raises(ValueError, match="id, name and description cannot be empty"):
        ActionRequest(**valeurs)


@pytest.mark.parametrize("vide", ["", "   "])
def test_action_request_refuse_un_contrat_blanc(vide):
    """`None` dit « aucun contrat » ; une chaine blanche ne dit rien du tout.

    Le gouverneur compare `action.contract_id` au contrat de mission et laisse
    passer `None` -- « pas de contrat precis ». Une chaine blanche ne serait ni l'un
    ni l'autre : elle ne correspondrait a aucune mission tout en pretendant en
    nommer une.
    """
    with pytest.raises(ValueError, match="contract_id cannot be blank"):
        ActionRequest("bounded", "bounded action", 1, 1, 9, contract_id=vide)


@pytest.mark.parametrize("vide", ["", "   "])
def test_action_request_refuse_une_capacite_blanche(vide):
    """La capacite **nommee**, celle que la politique resout dans son registre."""
    with pytest.raises(ValueError, match="capability cannot be blank"):
        ActionRequest("bounded", "bounded action", 1, 1, 9, capability=vide)


@pytest.mark.parametrize("vide", ["", "   "])
def test_action_request_refuse_un_jeton_d_execution_blanc(vide):
    with pytest.raises(ValueError, match="execution_capability cannot be blank"):
        ActionRequest("bounded", "bounded action", 1, 1, 9, execution_capability=vide)


@pytest.mark.parametrize("jeton", ["handler", "exec_1", "CAP_x", " cap_x"])
def test_action_request_exige_un_jeton_opaque(jeton):
    """Le jeton d'execution n'est pas un nom : c'est une cle de registre.

    Le prefixe `cap_` est ce qui distingue « quel code » de « est-ce permis ». La
    frontiere refuse deja une decision dont la cible n'a pas ce prefixe ; ici c'est
    refuse a la source, sur l'action elle-meme.
    """
    with pytest.raises(ValueError, match="must be an opaque cap_ token"):
        ActionRequest("bounded", "bounded action", 1, 1, 9, execution_capability=jeton)
