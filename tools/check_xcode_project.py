"""Vérifie que ios/SingularSage.xcodeproj est ouvrable et complet.

Le projet est écrit à la main, dans un environnement sans Xcode : personne ici
ne peut l'ouvrir pour voir s'il tient. Un projet corrompu bloquerait la
personne qui compile plus tôt encore que du Swift qui ne compile pas, et sans
message utile — Xcode dit seulement « the project is damaged ».

Ce script tient lieu de cette ouverture. Il analyse le `project.pbxproj` comme
un plist OpenStep, puis vérifie ce qu'Xcode vérifierait :

* la syntaxe : accolades, parenthèses, chaînes, point-virgules ;
* les références : tout identifiant cité correspond à un objet défini ;
* l'arborescence : chaque fichier du projet existe vraiment sur le disque ;
* le contenu : les sources compilées, les ressources embarquées et le lien
  entre la cible de tests et l'application qui l'héberge.

Il ne remplace pas une compilation. Il élimine la classe de pannes dont on ne
peut rien apprendre à distance.
"""
from __future__ import annotations

import pathlib
import sys

PROJECT = pathlib.Path(__file__).resolve().parent.parent / "ios/SingularSage.xcodeproj/project.pbxproj"


class ParseError(Exception):
    pass


def parse(text: str):
    """Analyse un plist OpenStep. Rend dictionnaires, listes et chaînes."""
    i = 0
    n = len(text)

    def skip():
        nonlocal i
        while i < n:
            if text[i] in " \t\r\n":
                i += 1
            elif text.startswith("//", i):
                i = text.find("\n", i)
                if i == -1:
                    i = n
            elif text.startswith("/*", i):
                end = text.find("*/", i)
                if end == -1:
                    raise ParseError("commentaire non fermé")
                i = end + 2
            else:
                return

    def value():
        nonlocal i
        skip()
        if i >= n:
            raise ParseError("fin de fichier inattendue")
        if text[i] == "{":
            i += 1
            out = {}
            while True:
                skip()
                if i < n and text[i] == "}":
                    i += 1
                    return out
                key = value()
                skip()
                if i >= n or text[i] != "=":
                    raise ParseError(f"« = » attendu après {key!r}")
                i += 1
                out[key] = value()
                skip()
                if i < n and text[i] == ";":
                    i += 1
                else:
                    raise ParseError(f"« ; » attendu après la valeur de {key!r}")
        if text[i] == "(":
            i += 1
            out = []
            while True:
                skip()
                if i < n and text[i] == ")":
                    i += 1
                    return out
                out.append(value())
                skip()
                if i < n and text[i] == ",":
                    i += 1
                elif i < n and text[i] == ")":
                    i += 1
                    return out
                else:
                    raise ParseError("« , » ou « ) » attendu dans une liste")
        if text[i] == '"':
            i += 1
            buf = []
            while i < n and text[i] != '"':
                if text[i] == "\\":
                    i += 1
                buf.append(text[i])
                i += 1
            if i >= n:
                raise ParseError("chaîne non fermée")
            i += 1
            return "".join(buf)
        start = i
        while i < n and (text[i].isalnum() or text[i] in "_$/.-"):
            i += 1
        if start == i:
            raise ParseError(f"caractère inattendu {text[i]!r} en position {i}")
        return text[start:i]

    root = value()
    skip()
    if i != n:
        raise ParseError(f"texte en trop après l'objet racine (position {i})")
    return root


def resolve_path(objects: dict, oid: str, base: pathlib.Path) -> pathlib.Path | None:
    """Le chemin disque d'une référence, en remontant ses groupes parents."""
    node = objects[oid]
    if node.get("sourceTree") == "BUILT_PRODUCTS_DIR":
        return None  # produit de compilation : il n'existe pas avant de compiler
    parts = [node["path"]] if "path" in node else []
    child = oid
    while True:
        parent = next((k for k, v in objects.items()
                       if v.get("isa") == "PBXGroup" and child in v.get("children", [])), None)
        if parent is None:
            break
        if "path" in objects[parent]:
            parts.insert(0, objects[parent]["path"])
        child = parent
    return base.joinpath(*parts) if parts else None


def main() -> int:
    problems: list[str] = []

    if not PROJECT.exists():
        print(f"absent : {PROJECT}")
        return 1

    try:
        root = parse(PROJECT.read_text(encoding="utf-8"))
    except ParseError as error:
        print(f"le projet ne s'analyse pas - Xcode dirait « damaged » : {error}")
        return 1

    objects = root["objects"]
    base = PROJECT.parent.parent  # le dossier ios/, où le .xcodeproj est posé

    # Toute référence doit pointer sur un objet défini.
    def walk(node, trail):
        if isinstance(node, dict):
            for key, item in node.items():
                walk(item, f"{trail}.{key}")
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{trail}[{index}]")
        elif isinstance(node, str) and len(node) == 24 and all(c in "0123456789ABCDEF" for c in node):
            if node not in objects:
                problems.append(f"{trail} cite {node}, qui n'est défini nulle part")

    walk(root, "root")

    # Chaque fichier du projet doit exister sur le disque.
    for oid, node in objects.items():
        if node.get("isa") != "PBXFileReference":
            continue
        path = resolve_path(objects, oid, base)
        if path is not None and not path.exists():
            problems.append(f"{node.get('path')} est dans le projet mais absent du disque ({path})")

    # Les fichiers du dépôt doivent tous être dans le projet, sinon on compile
    # un sous-ensemble sans le savoir.
    in_project = {resolve_path(objects, oid, base) for oid, node in objects.items()
                  if node.get("isa") == "PBXFileReference"}
    for path in sorted((base / "SingularSage").rglob("*")):
        if path.suffix in {".swift", ".json"} and path not in in_project:
            problems.append(f"{path.relative_to(base)} est sur le disque mais absent du projet")

    targets = {node["name"]: node for node in objects.values() if node.get("isa") == "PBXNativeTarget"}
    for expected in ("SingularSage", "SingularSageTests"):
        if expected not in targets:
            problems.append(f"la cible {expected} manque")
    if problems:
        for problem in problems:
            print(f"  - {problem}")
        return 1

    # Ce que chaque phase embarque réellement.
    def phase_files(target: dict, isa: str) -> set[str]:
        out = set()
        for phase_id in target["buildPhases"]:
            phase = objects[phase_id]
            if phase.get("isa") != isa:
                continue
            for build_file in phase.get("files", []):
                ref = objects[build_file]["fileRef"]
                out.add(objects[ref]["path"])
        return out

    app_sources = phase_files(targets["SingularSage"], "PBXSourcesBuildPhase")
    test_sources = phase_files(targets["SingularSageTests"], "PBXSourcesBuildPhase")
    test_resources = phase_files(targets["SingularSageTests"], "PBXResourcesBuildPhase")

    if "notice_vectors.json" not in test_resources:
        problems.append("notice_vectors.json n'est pas embarqué dans le bundle de test : "
                        "les tests de portage ne pourraient rien vérifier")
    for name in ("Journal.swift", "Notice.swift", "Entry.swift", "Tier.swift"):
        if name not in app_sources:
            problems.append(f"{name} n'est pas compilé dans l'application")
    if not test_sources:
        problems.append("la cible de tests ne compile aucun fichier")

    # Un fichier compilé deux fois donnerait « duplicate symbol » au lien.
    overlap = app_sources & test_sources
    if overlap:
        problems.append(f"compilé à la fois dans l'app et dans les tests : {sorted(overlap)}")

    # Les tests utilisent `@testable import`, ce qui exige d'être hébergé par
    # l'app et de la construire d'abord.
    tests_settings = {}
    for config_id in objects[targets["SingularSageTests"]["buildConfigurationList"]]["buildConfigurations"]:
        tests_settings.update(objects[config_id]["buildSettings"])
    if "TEST_HOST" not in tests_settings:
        problems.append("la cible de tests n'a pas de TEST_HOST : « @testable import » échouerait")
    if not targets["SingularSageTests"].get("dependencies"):
        problems.append("la cible de tests ne dépend pas de l'application")
    # Un bundle de test est chargé par son hôte, pas lancé : sans @loader_path
    # il ne retrouve pas XCTest, et l'échec arrive à l'exécution, pas au
    # linkage — donc après une compilation qui a l'air d'avoir réussi.
    runpath = tests_settings.get("LD_RUNPATH_SEARCH_PATHS", [])
    if "@loader_path/Frameworks" not in runpath:
        problems.append("la cible de tests n'a pas @loader_path/Frameworks dans "
                        "LD_RUNPATH_SEARCH_PATHS : le bundle ne trouverait pas XCTest")

    # Le mode de langage doit être écrit, pas hérité de la version d'Xcode
    # installée : c'est exactement ce que ce projet existe pour fixer.
    project_settings = {}
    project = next(node for node in objects.values() if node.get("isa") == "PBXProject")
    for config_id in objects[project["buildConfigurationList"]]["buildConfigurations"]:
        project_settings.update(objects[config_id]["buildSettings"])
    if "SWIFT_VERSION" not in project_settings:
        problems.append("SWIFT_VERSION n'est pas fixé : le mode de langage dépendrait d'Xcode")
    if "IPHONEOS_DEPLOYMENT_TARGET" not in project_settings:
        problems.append("IPHONEOS_DEPLOYMENT_TARGET n'est pas fixé")

    for problem in problems:
        print(f"  - {problem}")
    if problems:
        return 1

    print(f"projet valide : {len(objects)} objets, "
          f"{len(app_sources)} sources dans l'app, {len(test_sources)} dans les tests, "
          f"Swift {project_settings['SWIFT_VERSION']}, "
          f"iOS {project_settings['IPHONEOS_DEPLOYMENT_TARGET']} minimum")
    return 0


if __name__ == "__main__":
    sys.exit(main())
