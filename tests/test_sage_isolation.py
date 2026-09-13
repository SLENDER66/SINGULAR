"""Le Sage observe et conseille. Il ne doit pas pouvoir agir sur le monde.

C'est l'invariant central du dépôt appliqué à la surface qui parle :
penser n'est pas décider, décider n'est pas autoriser, autoriser n'est pas
exécuter. Le Sage occupe la première case, et ce test empêche la quatrième de
s'y glisser -- par un import ajouté sans y penser, par une fonctionnalité qui
« aurait juste besoin de lancer une action ».

Le jour où le Sage devra vraiment agir, ce test échouera. C'est voulu : ce sera
le moment de passer par la frontière validée, décision attestée comprise, et
pas de la contourner parce qu'un serveur HTTP avait la main.

Ce fichier a promis « directement ou non » pendant des semaines en ne lisant que
les imports directs des fichiers de `singular/sage/`. Trois chemins le
traversaient donc sans le faire rougir, et ce ne sont pas des hypothèses -- les
trois ont été construits et mesurés :

1. un import ajouté dans une faculté que le Sage charge. `improvement_registry`
   importé depuis `analyse.py` : la suite entière restait verte ;
2. `importlib.import_module("singular.autopilot")` dans le Sage lui-même. Le
   fichier ne lisait pas les appels, et le Sage utilise déjà cet idiome pour
   charger `offres` ;
3. `singular.mission_runtime` en accès d'attribut, sans instruction d'import :
   `singular/__init__.py` résout ses noms à la demande, donc ça suffit.

Un garde qui annonce plus qu'il ne vérifie est pire qu'un garde absent : il fait
croire la propriété acquise. Il lit maintenant la fermeture des imports du
paquet, les appels d'import dynamiques et les attributs de `singular`, et il
nomme la chaîne quand il refuse.
"""
from __future__ import annotations

import ast
from pathlib import Path

from singular.execution_boundary_audit import EXECUTION_CAUSING_MODULES

SAGE = Path(__file__).resolve().parent.parent / "singular" / "sage"

#: Les modules qui mènent à une exécution durable, directement ou non.
#:
#: `validated_decision_service` manquait, et c'était le plus mal choisi des
#: oublis : c'est la façade qui enchaîne construction, attestation et exécution,
#: donc le chemin le plus court du dépôt entre « avoir un objet » et « le monde a
#: changé ». L'auditeur du paquet le nommait, cette liste non, et rien ne
#: comparait les deux -- le dernier test de ce fichier le fait maintenant.
EXECUTION_MODULES = frozenset({
    "execution", "validated_execution", "durable_execution", "execution_capability",
    "reconciled_execution", "tool_fabric", "autopilot", "mission_autopilot", "empire",
    "effects", "durable", "mission_runtime", "control_plane", "validated_pipeline",
    "decision_attestation", "validated_trajectory_decision", "agent_orchestration",
    "production_runtime", "improvement_registry", "self_improvement",
    "validated_decision_service",
})

#: Ce que le Sage a le droit de lire.
#:
#: `analyse` et `parle` y sont entrés le jour où la conversation a été servie
#: depuis le téléphone, et c'est une décision, pas une dérive : Thomas l'a
#: demandée, avec un plafond quotidien. Ce qu'elles ajoutent est un appel à un
#: modèle, qui rend du texte -- pas un pouvoir d'agir. Ni l'une ni l'autre
#: n'importe la frontière d'exécution, ni le journal pour `parle` : le test
#: au-dessus continue de le vérifier, et c'est lui qui porte l'invariant.
#:
#: `offres` y est entré ensuite, pour la même raison et sous les mêmes gardes :
#: il lit des annonces, il écarte, il propose. Il ne postule jamais et il
#: n'importe pas le journal -- « l'autorité reste moi, toujours, avant toute
#: action », et c'est le test au-dessus qui le tient, pas cette phrase. Il
#: partage le verrou de la conversation : même porte-monnaie, donc une seule
#: dépense à la fois.
#:
#: Ce que ça coûte, écrit ici pour que personne n'ait à le redécouvrir : une
#: route du Sage peut dépenser de l'argent. Elle refuse sans clé, une seule
#: dépense à la fois, `parle.PLAFOND_PAR_JOUR` par jour -- le nombre n'est pas
#: recopié ici, il l'a déjà été et il avait vieilli -- et le reste de l'app
#: continue quand elle est coupée : `test_sage_parle.py` et
#: `test_sage_offres.py` le vérifient plutôt que de le promettre.
#: `saisie` y est entre pour que les refus soient dits dans sa langue : la
#: regle est celle du journal, la phrase est ecrite une fois, et les deux
#: surfaces la lisent au lieu de la reecrire. Il ne lit rien, il n'ecrit rien.
#:
#: `fichiers` y est entre pour une raison plus etroite encore : savoir ecrire
#: un fichier sans pouvoir le perdre en tombant. Il n'importe que `os` et
#: `pathlib`, il ne lit rien, il ne decide rien -- et il porte la seule
#: ecriture atomique du depot, celle que la cle d'acces utilise pour ne pas
#: exister un instant en clair.
#:
#: `collecte` est le Scout, et il elargit ce que le Sage **lit** : c'est la
#: premiere fois qu'une donnee entre dans l'app sans venir du journal. Ce que
#: ca coute, ecrit ici pour que personne n'ait a le rechercher : le Sage lit
#: desormais aussi `~/.singular/candidatures.json`, en lecture seule, sans
#: reseau et sans jeton. Le Scout n'a aucun moyen d'ecrire -- ni `write_text`,
#: ni `open` en ecriture, ni le journal -- et `tests/test_collecte.py` le
#: verifie sur l'arbre syntaxique plutot que sur sa docstring. Il ne juge pas
#: non plus : un seuil de relance est un jugement, il reste chez celui qui
#: juge. Le Sage gagne donc un fait de plus a montrer, et aucun pouvoir.
ALLOWED = frozenset({"journal", "sage", "icon", "notice", "server", "learning",
                     "collecte",
                     "sqlite_support", "analyse", "parle", "offres", "fichiers",
                     "saisie"})


def _imports_du_paquet(source: Path) -> set[str]:
    """Les modules du paquet que ce fichier met à portée, par tous les chemins d'ici.

    Trois façons de nommer un module coexistent dans ce dépôt, et une seule
    était lue : l'instruction `import`. Les deux autres ne sont pas
    hypothétiques -- `sage/server.py` charge `offres` par
    `importlib.import_module`, exprès, et `singular/__init__.py` résout ses noms
    à la demande, donc `singular.execution` se lit aussi en attribut. Une règle
    qui ne voit qu'une des trois n'interdit rien : elle indique par où passer.

    Reste dehors ce qu'aucune lecture statique ne résout : un nom de module
    calculé à l'exécution (`import_module(f"singular.{nom}")`). C'est la limite
    connue de l'empreinte de capability, et elle est la même ici.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                found.add(node.module.split(".")[-1])
            # `from . import offres` et `from singular import offres` nomment
            # des modules dans leurs alias, pas dans leur module.
            if (node.level and node.module is None) or node.module == "singular":
                found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("singular"):
                    found.add(alias.name.split(".")[-1])
        elif isinstance(node, ast.Call):
            found |= _noms_importes_dynamiquement(node)
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "singular":
                found.add(node.attr)
    return found


def _noms_importes_dynamiquement(node: ast.Call) -> set[str]:
    """Les segments d'un module nommé par une chaîne littérale.

    `importlib.import_module("singular.execution")` est un import ; le lire
    comme un appel anodin suffisait à traverser ce fichier.
    """
    func = node.func
    called = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
    if called not in {"import_module", "__import__"}:
        return set()
    argument = node.args[0] if node.args else None
    if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
        return set()
    return set(argument.value.split("."))


def _modules_du_paquet() -> dict[str, Path]:
    return {path.stem: path for path in sorted(SAGE.parent.glob("*.py"))}


def _portee_du_sage() -> dict[str, tuple[str, ...]]:
    """Chaque module du paquet que le Sage atteint, et la chaîne qui y mène.

    Le Sage n'exécute pas seulement ce qu'il importe : il exécute aussi ce
    qu'importe ce qu'il importe. Vérifier ses seuls imports directs laissait la
    porte grande ouverte -- un import ajouté dans `analyse.py`, que le Sage
    charge, et la frontière d'exécution était à sa portée avec toute la suite au
    vert. Mesuré, pas supposé : `improvement_registry` est passé ainsi.

    La chaîne est retournée avec le module pour que l'échec nomme le chemin
    plutôt que le seul coupable final.
    """
    modules = _modules_du_paquet()
    atteints: dict[str, tuple[str, ...]] = {}
    file: list[tuple[str, tuple[str, ...]]] = []
    for source in sorted(SAGE.rglob("*.py")):
        depart = f"sage/{source.relative_to(SAGE).as_posix()}"
        for nom in sorted(_imports_du_paquet(source)):
            file.append((nom, (depart,)))
    while file:
        nom, chaine = file.pop(0)
        if nom not in modules or nom in atteints:
            continue
        atteints[nom] = chaine + (nom,)
        for suivant in sorted(_imports_du_paquet(modules[nom])):
            file.append((suivant, atteints[nom]))
    return atteints


def _chaine(chemin: tuple[str, ...]) -> str:
    return " -> ".join(chemin)


def test_the_sage_never_imports_the_execution_boundary():
    portee = _portee_du_sage()
    interdits = {nom: chemin for nom, chemin in portee.items() if nom in EXECUTION_MODULES}
    assert not interdits, (
        "le Sage atteint la frontière d'exécution : "
        + " ; ".join(_chaine(chemin) for _, chemin in sorted(interdits.items()))
        + ". Le Sage conseille, il n'exécute pas. Si une action sur le monde est vraiment "
        "nécessaire, elle passe par une décision validée et attestée, pas par un import "
        "ajouté quelque part sur ce chemin."
    )
    assert len(list(SAGE.rglob("*.py"))) >= 4, "le test doit voir les modules du Sage, pas un dossier vide"
    assert "journal" in portee, "le test doit voir ce que le Sage lit, pas un graphe vide"


def test_what_the_sage_reads_is_declared():
    """Une dépendance nouvelle doit être un choix, pas un effet de bord.

    Y compris une dépendance contractée pour lui par une faculté : ce que le
    Sage lit vraiment est la fermeture de ses imports, pas la première ligne.
    """
    portee = _portee_du_sage()
    non_declares = {nom: chemin for nom, chemin in portee.items() if nom not in ALLOWED}
    assert not non_declares, (
        "le Sage atteint des modules non déclarés dans ALLOWED : "
        + " ; ".join(_chaine(chemin) for _, chemin in sorted(non_declares.items()))
    )


def test_ce_que_l_auditeur_interdit_au_paquet_est_interdit_au_sage():
    """Deux listes de « ce qui mène à l'exécution » vivaient sans se connaître.

    `EXECUTION_CAUSING_MODULES`, dans l'auditeur, gouverne tout le paquet ;
    celle d'ici gouverne le Sage et en nomme davantage. Rien ne liait les deux :
    un module ajouté à l'une pouvait manquer à l'autre pendant des mois, et
    c'est exactement de cet écart que vit un chemin caché. Le lien est
    maintenant vérifié dans le sens qui compte -- ce que l'auditeur juge capable
    de déclencher une exécution ne peut pas être absent d'ici.
    """
    assert EXECUTION_CAUSING_MODULES <= EXECUTION_MODULES, sorted(EXECUTION_CAUSING_MODULES - EXECUTION_MODULES)
