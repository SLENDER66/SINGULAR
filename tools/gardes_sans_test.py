"""Quel refus de la frontiere peut-on retirer sans qu'aucun test ne rougisse ?

« Les tests passent » ne dit pas quels refus sont prouves. Cet outil le mesure :
il neutralise chaque `if ... raise` des modules de la frontiere, un par un, en
rendant sa condition fausse, relance une sous-suite ciblee, et nomme ceux qui
survivent. Un survivant est un refus qu'aucun test n'atteint.

**Un survivant est une question, pas un defaut.** Trois reponses possibles, et il
faut choisir la bonne avant d'ecrire une ligne :

1. *Le refus est atteignable et personne ne l'essaie.* C'est un trou. Ecris le
   test. La reconciliation etait dans ce cas : la substitution de fournisseur,
   d'operation et de charge etait testee a l'aller et pas au retour, alors que la
   reconciliation atteint le meme fournisseur et peut faire passer une execution
   a COMPLETED.
2. *Le refus ne peut pas se declencher parce qu'un controle anterieur le couvre.*
   La plupart des refus de `validated_execution.py` sont dans ce cas : une
   decision qui les violerait a une empreinte differente, donc `verify()` la
   refuse avant. Ce sont des assurances, pas des trous. Leur ecrire un test
   demanderait de desactiver `verify()`, donc de tester un chemin qui n'existe
   pas -- ce que la regle 18 du depot appelle un test suspect.
3. *Le refus ne peut pas se declencher parce que rien ne produit son entree.*
   Les quatre refus lies a l'approbation humaine sont dans ce cas : une decision
   validee ne peut pas porter ESCALATE, donc aucune execution escaladee n'atteint
   la frontiere. C'est ce que le README annonce -- « human approval is currently
   not an authorization channel » -- et cet outil le mesure au lieu de le croire.

Il ne tourne pas dans le CI : une passe complete prend une dizaine de minutes.
C'est un instrument d'audit, a relancer quand on touche a la frontiere.

    python3 tools/gardes_sans_test.py

Le depot n'est jamais laisse modifie : chaque fichier est restaure avant le
mutant suivant, et dans un `finally`. Si le processus est tue en cours,
`git checkout -- singular/` remet tout.
"""
from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

RACINE = pathlib.Path(__file__).resolve().parent.parent

#: Les modules qui portent la frontiere : decision, autorisation, execution, effet.
CIBLES = (
    "singular/execution.py",
    "singular/validated_execution.py",
    "singular/validated_trajectory_decision.py",
    "singular/decision_attestation.py",
    "singular/execution_capability.py",
    "singular/effects.py",
)

#: La sous-suite qui couvre ces modules. Ciblee exprès : la suite entiere prend
#: 70 secondes, et il faut la relancer une fois par refus.
SOUS_SUITE = (
    "tests/test_validated_execution.py", "tests/test_validated_trajectory_decision.py",
    "tests/test_execution_bypass_resistance.py", "tests/test_validated_boundary_invariants.py",
    "tests/test_decision_execution_binding.py", "tests/test_validated_capability_binding.py",
    "tests/test_capability_durable_identity.py", "tests/test_capability_code_identity.py",
    "tests/test_capability_declared_identity.py", "tests/test_capability_registry_lifecycle.py",
    "tests/test_capability_field_separation.py", "tests/test_decision_attestation.py",
    "tests/test_adversarial.py", "tests/test_v47_adversarial_core.py",
    "tests/test_strict_execution_boundary_effects.py", "tests/test_effect_execution_boundary.py",
    "tests/test_execution_capability.py", "tests/test_effect_capability_time_of_use.py",
    "tests/test_effect_reconciliation_boundary.py", "tests/test_reconciliation_policy_drift.py",
    "tests/test_recovery_finalization.py", "tests/test_recovery_consistency.py",
    "tests/test_durable_execution.py", "tests/test_execution_boundary_audit.py",
    "tests/test_v34_execution.py", "tests/test_v39_effect_execution.py",
    "tests/test_v38_external_effects.py", "tests/test_v50_effect_races.py",
    "tests/test_validated_pipeline.py", "tests/test_validated_decision_service.py",
    "tests/test_approval_durability.py", "tests/test_no_raw_execution_call_sites.py",
    "tests/test_decision_serialization_guard.py", "tests/test_action_request_validation.py",
    "tests/test_le_moteur_refuse_de_lui_meme.py",
)

#: Les exceptions qui disent « refuse ». Une `KeyError` ou une `AttributeError`
#: n'est pas un refus, c'est un accident -- on ne les mute pas.
REFUS = frozenset({"PermissionError", "ValueError", "RuntimeError", "TypeError"})


class RendLaConditionFausse(ast.NodeTransformer):
    def __init__(self, ligne: int) -> None:
        self.ligne = ligne
        self.touche = False

    def visit_If(self, node: ast.If) -> ast.If:
        self.generic_visit(node)
        if node.test.lineno == self.ligne and not node.orelse:
            node.test = ast.Constant(value=False)
            self.touche = True
        return node


def refus_d_un_fichier(arbre: ast.AST) -> list[tuple[int, str]]:
    """Les `if <condition>: raise <refus>` d'un module, par ligne de condition."""
    trouves = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.If) or noeud.orelse:
            continue
        if len(noeud.body) != 1 or not isinstance(noeud.body[0], ast.Raise):
            continue
        leve = noeud.body[0].exc
        nom = ""
        if isinstance(leve, ast.Call):
            nom = getattr(leve.func, "id", "") or getattr(leve.func, "attr", "")
        if nom in REFUS:
            trouves.append((noeud.test.lineno, nom))
    return trouves


def _la_sous_suite_passe() -> bool:
    acheve = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
         "-p", "no:randomly", *SOUS_SUITE],
        capture_output=True, text=True, cwd=RACINE, check=False,
    )
    return acheve.returncode == 0


def main() -> int:
    if not _la_sous_suite_passe():
        print("la sous-suite echoue deja sans mutant : rien a mesurer", file=sys.stderr)
        return 2
    survivants = 0
    total = 0
    for cible in CIBLES:
        chemin = RACINE / cible
        original = chemin.read_text(encoding="utf-8")
        lignes = original.split("\n")
        try:
            for ligne, refus in refus_d_un_fichier(ast.parse(original)):
                total += 1
                mutant = RendLaConditionFausse(ligne)
                arbre = mutant.visit(ast.parse(original))
                if not mutant.touche:
                    continue
                ast.fix_missing_locations(arbre)
                chemin.write_text(ast.unparse(arbre), encoding="utf-8")
                if _la_sous_suite_passe():
                    survivants += 1
                    print(f"SURVIT  {cible}:{ligne}  {refus}  {lignes[ligne - 1].strip()[:100]}", flush=True)
                chemin.write_text(original, encoding="utf-8")
        finally:
            chemin.write_text(original, encoding="utf-8")
    print(f"\n{survivants} refus survivant(s) sur {total} mutes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
