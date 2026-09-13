"""Une transition du store appartient a qui tient le store, pas a qui importe bien.

`confirm_execution_recovery_from_effect` gouverne RECOVERY_REQUIRED -> COMPLETED :
le seul passage qui transforme un effet externe ambigu en succes durable. Elle
vivait dans `durable_recovery.py` et etait greffee sur la classe a l'import.

Donc elle etait **absente** de tout processus qui n'importait pas ce module -- et
le moteur d'execution est l'un d'eux : il l'appelle a trois endroits et n'importe
rien qui l'installe. Une reconciliation qui venait de prouver que l'effet avait
abouti mourait sur `AttributeError`, en laissant l'execution RECOVERY_REQUIRED et
la mission RUNNING pour toujours, l'effet deja parti dans le monde.

La suite entiere le cachait : un fichier de tests importait `durable_recovery`,
ce qui greffait la methode pour tous les tests suivants. Lance seul, le test
adversarial de ce chemin precis echouait -- et `mypy` le disait depuis le debut,
a l'etape du CI qui n'est qu'informative.

L'integrite des approbations etait arrivee de la meme facon et avait ete
rapatriee dans la classe pour la meme raison. La troisieme fois ne se corrige
pas : le mecanisme de greffe n'existe plus, et le dernier test de ce fichier
refuse son retour.
"""
from __future__ import annotations

import ast
import pathlib
import subprocess
import sys
import textwrap

import pytest

from singular.autopilot import ApprovalRequest, ApprovalStatus, Autonomy, DelegationContract
from singular.durable import DurableStore

PAQUET = pathlib.Path(__file__).resolve().parent.parent / "singular"

#: Les transitions qu'aucun import ne doit pouvoir ajouter ni retirer.
TRANSITIONS = (
    "confirm_execution_recovery_from_effect",
    "resolve_execution_recovery",
    "mark_execution_recovery_required",
    "recover_stale_execution",
    "finish_execution_and_mission",
    "begin_execution_and_start_mission",
    "save_approval",
    "update_approval",
)


@pytest.mark.parametrize("nom", TRANSITIONS)
def test_chaque_transition_est_definie_par_la_classe_elle_meme(nom: str):
    methode = getattr(DurableStore, nom)
    assert methode.__module__ == "singular.durable", (
        f"DurableStore.{nom} vient de {methode.__module__} : une transition greffee "
        "depuis ailleurs est absente des processus qui n'importent pas ce module."
    )


def test_la_transition_de_recuperation_existe_pour_qui_n_importe_que_la_frontiere():
    """Le temoin qui manquait, ecrit comme le defaut se produisait : un processus neuf.

    Sous-processus exprès. Dans celui-ci, un autre fichier de tests a deja pu
    importer n'importe quoi, et c'est precisement ce qui cachait le defaut.
    """
    code = textwrap.dedent(
        """
        from singular.validated_execution import ValidatedExecutionBoundary  # la surface recommandee
        from singular.durable import DurableStore

        methode = getattr(DurableStore, "confirm_execution_recovery_from_effect", None)
        print("ABSENTE" if methode is None else methode.__module__)
        """
    )
    sortie = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=PAQUET.parent)
    assert sortie.returncode == 0, sortie.stderr
    assert sortie.stdout.strip() == "singular.durable", sortie.stdout


def test_aucun_module_ne_greffe_une_methode_sur_le_store():
    """Le mecanisme est parti ; ce test refuse qu'il revienne sous un autre nom.

    Il ne cherche pas `install_store_extension` -- un nom disparu n'a pas besoin
    d'etre garde. Il cherche le geste : attacher un attribut a `DurableStore`
    depuis l'exterieur de sa classe.
    """
    fautes: list[str] = []
    for fichier in sorted(PAQUET.rglob("*.py")):
        arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name) and noeud.func.id == "setattr":
                premier = noeud.args[0] if noeud.args else None
                if isinstance(premier, ast.Name) and premier.id == "DurableStore":
                    fautes.append(f"{fichier.name}:{noeud.lineno}: setattr(DurableStore, ...)")
            if isinstance(noeud, ast.Assign):
                for cible in noeud.targets:
                    if (isinstance(cible, ast.Attribute) and isinstance(cible.value, ast.Name)
                            and cible.value.id == "DurableStore"):
                        fautes.append(f"{fichier.name}:{noeud.lineno}: DurableStore.{cible.attr} = ...")
    assert not fautes, (
        "une transition greffee est absente des processus qui n'importent pas le greffon : "
        + ", ".join(fautes)
    )


def test_approval_identity_is_immutable_without_any_import_beyond_the_store(tmp_path):
    """The guarantee has to hold for whoever holds a DurableStore, not for whoever imported well."""
    store = DurableStore(tmp_path / "approvals.db")
    store.save_mission(DelegationContract("MIS-A", "objective", "expected", autonomy=Autonomy.PREPARE))
    approval = ApprovalRequest("ACT-1", "because", id="APP-1")
    store.save_approval(approval, "MIS-A")

    with pytest.raises(ValueError, match="immuable"):
        store.save_approval(ApprovalRequest("ACT-OTHER", "because", id="APP-1"), "MIS-A")

    store.update_approval("APP-1", ApprovalStatus.REJECTED)
    with pytest.raises(ValueError, match="Transition d'approbation interdite"):
        store.update_approval("APP-1", ApprovalStatus.APPROVED)
