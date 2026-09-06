"""Le port doit pouvoir décoder les vecteurs qu'on lui envoie.

`NoticeVectorTests.swift` déclare des structures `Decodable` qui doivent
correspondre, clé pour clé, au JSON que `generate_notice_vectors.py` produit.
Rien ne relie les deux fichiers : ajouter un champ au générateur sans le
déclarer côté Swift ne casse rien ici, et se paie sur le Mac — soit par un
`keyNotFound` qui arrête tous les vecteurs d'un coup, soit, pire, par un champ
que le port ignore en silence en croyant vérifier quelque chose.

C'est arrivé en ajoutant `chain_intact`. Le coût d'un aller-retour n'est pas
un test rouge de plus : c'est une heure de la journée de quelqu'un d'autre, et
un Mac qu'on ne contrôle pas. D'où ce test, qui lit le Swift plutôt que de
faire confiance à qui l'édite.

Il ne compile pas le Swift — il le lit. Une déclaration écrite autrement que
celles d'aujourd'hui lui échapperait, et c'est pourquoi il exige d'abord
d'avoir trouvé ce qu'il cherchait.
"""
from __future__ import annotations

import json
import pathlib
import re

from tools.generate_notice_vectors import build_vectors

SWIFT = (pathlib.Path(__file__).resolve().parent.parent
         / "ios/SingularSage/Tests/NoticeVectorTests.swift")

#: Structure Swift → un exemple du fragment JSON qu'elle décode.
BINDINGS = {
    "VectorFile": lambda doc: doc,
    "Case": lambda doc: doc["cases"][0],
    "VectorEntry": lambda doc: next(c["entries"][0] for c in doc["cases"] if c["entries"]),
    "Expectation": lambda doc: doc["cases"][0]["expected"],
    "ExpectedItem": lambda doc: next(c["expected"]["items"][0] for c in doc["cases"]
                                     if c["expected"]["items"]),
}

#: Ce que le port ignore délibérément : de la provenance pour un lecteur humain.
IGNORED_BY_DESIGN = {"VectorFile": {"generated_by", "note"}}


def _block(source: str, name: str) -> str:
    """Le corps d'une déclaration, accolades équilibrées."""
    start = source.index(f"struct {name}: Decodable {{")
    depth, index = 0, source.index("{", start)
    for position in range(index, len(source)):
        depth += {"{": 1, "}": -1}.get(source[position], 0)
        if depth == 0:
            return source[index + 1:position]
    raise AssertionError(f"accolade non fermée dans struct {name}")


def _declared_keys(source: str, name: str) -> dict[str, bool]:
    """Les clés JSON qu'une structure attend, et si chacune est obligatoire.

    Une propriété optionnelle peut manquer du JSON sans faire échouer le
    décodage ; une autre non.
    """
    body = _block(source, name)
    coding = re.search(r"enum CodingKeys[^{]*\{(.*?)\n\s*\}", body, re.S)
    renamed, plain = {}, []
    if coding:
        for line in coding.group(1).splitlines():
            line = line.strip()
            if not line.startswith("case "):
                continue
            for item in line[len("case "):].split(","):
                item = item.strip()
                if "=" in item:
                    swift, _, raw = item.partition("=")
                    renamed[swift.strip()] = raw.strip().strip('"')
                elif item:
                    plain.append(item)
        body = body[:coding.start()] + body[coding.end():]

    keys: dict[str, bool] = {}
    for swift_name, kind in re.findall(r"^\s*(?:let|var)\s+(\w+)\s*:\s*([^\n=]+)$",
                                       body, re.M):
        keys[renamed.get(swift_name, swift_name)] = not kind.strip().endswith("?")
    assert keys, f"aucune propriété trouvée dans struct {name} — le format a changé"
    if coding:
        declared = set(renamed) | set(plain)
        missing = {k for k in keys if k not in renamed.values()} - declared
        assert not missing, f"{name} : CodingKeys omet {sorted(missing)}"
    return keys


def test_the_swift_structures_still_match_the_generated_vectors() -> None:
    source = SWIFT.read_text(encoding="utf-8")
    document = json.loads(json.dumps(build_vectors()))
    assert set(BINDINGS) <= set(re.findall(r"struct (\w+): Decodable", source)), (
        "une structure attendue a disparu de NoticeVectorTests.swift")

    for name, locate in BINDINGS.items():
        expected = _declared_keys(source, name)
        present = set(locate(document))

        required = {key for key, mandatory in expected.items() if mandatory}
        assert required <= present, (
            f"{name} exige {sorted(required - present)}, que le JSON ne porte pas : "
            "le décodage échouerait sur tous les vecteurs à la fois")

        unread = present - set(expected) - IGNORED_BY_DESIGN.get(name, set())
        assert not unread, (
            f"{name} : le JSON porte {sorted(unread)} que le port ne lit pas. "
            "Déclare-le dans NoticeVectorTests.swift, ou range-le dans "
            "IGNORED_BY_DESIGN si c'est voulu")


def test_the_reader_would_notice_a_field_the_port_ignores() -> None:
    """Le témoin : sans lui, un parseur qui ne trouve rien passerait au vert."""
    keys = _declared_keys(SWIFT.read_text(encoding="utf-8"), "Case")
    assert keys["chain_intact"] is True, "chain_intact doit être lu et obligatoire"
    assert keys["name"] is True
    assert "chainIntact" not in keys, "le nom Swift ne doit pas servir de clé JSON"
