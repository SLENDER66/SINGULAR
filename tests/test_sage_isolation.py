"""Le Sage observe et conseille. Il ne doit pas pouvoir agir sur le monde.

C'est l'invariant central du dépôt appliqué à la surface qui parle :
penser n'est pas décider, décider n'est pas autoriser, autoriser n'est pas
exécuter. Le Sage occupe la première case, et ce test empêche la quatrième de
s'y glisser -- par un import ajouté sans y penser, par une fonctionnalité qui
« aurait juste besoin de lancer une action ».

Le jour où le Sage devra vraiment agir, ce test échouera. C'est voulu : ce sera
le moment de passer par la frontière validée, décision attestée comprise, et
pas de la contourner parce qu'un serveur HTTP avait la main.
"""
from __future__ import annotations

import ast
from pathlib import Path

SAGE = Path(__file__).resolve().parent.parent / "singular" / "sage"

#: Les modules qui mènent à une exécution durable, directement ou non.
EXECUTION_MODULES = frozenset({
    "execution", "validated_execution", "durable_execution", "execution_capability",
    "reconciled_execution", "tool_fabric", "autopilot", "mission_autopilot", "empire",
    "effects", "durable", "mission_runtime", "control_plane", "validated_pipeline",
    "decision_attestation", "validated_trajectory_decision", "agent_orchestration",
    "production_runtime", "improvement_registry", "self_improvement",
})

#: Ce que le Sage a le droit de lire.
ALLOWED = frozenset({"journal", "sage", "icon", "notice", "server", "learning", "sqlite_support"})


def _imported_modules(source: Path) -> set[str]:
    """Les modules du paquet que ce fichier importe, relatifs ou absolus."""
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[-1])
        elif isinstance(node, ast.ImportFrom) and node.level and node.module is None:
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("singular"):
                    found.add(alias.name.split(".")[-1])
    return found


def test_the_sage_never_imports_the_execution_boundary():
    checked = 0
    for source in sorted(SAGE.rglob("*.py")):
        checked += 1
        forbidden = _imported_modules(source) & EXECUTION_MODULES
        assert not forbidden, (
            f"{source.name} importe {sorted(forbidden)} : le Sage conseille, il n'exécute pas. "
            "Si une action sur le monde est vraiment nécessaire, elle passe par une décision "
            "validée et attestée, pas par un import ajouté ici."
        )
    assert checked >= 4, "le test doit voir les modules du Sage, pas un dossier vide"


def test_what_the_sage_reads_is_declared():
    """Une dépendance nouvelle doit être un choix, pas un effet de bord."""
    for source in sorted(SAGE.rglob("*.py")):
        undeclared = {
            name for name in _imported_modules(source)
            if name in {path.stem for path in SAGE.parent.glob("*.py")} and name not in ALLOWED
        }
        assert not undeclared, f"{source.name} importe {sorted(undeclared)}, non déclaré dans ALLOWED"
