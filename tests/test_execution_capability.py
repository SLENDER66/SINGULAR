from singular.execution_capability import ExecutionCapabilityRegistry

# Les `lambda` de ce fichier ne sont pas un raccourci, et `pyproject.toml` y tait
# E731 pour cette raison : deux lambdas ecrites cote a cote ont le meme
# `qualname` -- `<lambda>` -- donc la meme empreinte d'artefact. C'est ce qui
# rend le test honnete : quand `matches(capability, second)` refuse, il refuse un
# objet que rien ne distingue du premier, ce qui prouve que la liaison porte sur
# l'objet. Deux `def` nommes `first` et `second` auraient deux empreintes, et le
# refus ne prouverait plus que le code differe. Mesure, pas suppose.


def test_registry_binds_to_exact_object_identity():
    registry = ExecutionCapabilityRegistry()
    first = lambda _action: None
    second = lambda _action: None
    capability = registry.register(first, "cap_exact_object")

    assert registry.matches(capability, first) is True
    assert registry.matches(capability, second) is False


def test_registry_rejects_token_collision_and_supports_revoke():
    """Le refus de collision, et la moitie qui n'a pas de temoin -- avec pourquoi.

    `if bound is not None and bound is not target` : ce test tue la premiere
    moitie, jamais la seconde. Neutralisee, la condition devient « le jeton est
    deja pris », ce qui refuse **aussi** la collision -- donc ce test passe
    quand meme. La seconde moitie ne decide que dans l'autre sens : le jeton est
    pris par **ce meme objet**, et il ne faut pas refuser.

    Cet etat n'a pas ete atteint, et trois chemins ont ete essayes le 15
    septembre 2026 : reinscrire le meme objet sous le meme jeton (retour
    anticipe par `_by_object`, la ligne n'est pas atteinte), le meme objet sous
    un second jeton (refuse un cran plus haut, « already bound to a different
    capability »), et une revocation suivie d'une reinscription (`bound` est
    alors None). `_targets` gardant une reference forte, `id()` ne peut pas etre
    reutilise par un autre objet tant que le premier est inscrit.

    C'est donc une moitie masquee, comme celle de `register(None)` decrite plus
    bas, et elle reste : la retirer sur « je n'ai pas trouve » plutot que sur
    « c'est impossible » irait dans le sens permissif, ce que la section 7 du
    mandat interdit.
    """
    registry = ExecutionCapabilityRegistry()
    first = lambda _action: None
    second = lambda _action: None
    registry.register(first, "cap_collision")

    try:
        registry.register(second, "cap_collision")
    except ValueError:
        pass
    else:
        raise AssertionError("capability collision must be rejected")

    registry.revoke("cap_collision")
    assert registry.matches("cap_collision", first) is False


# --- ce que le registre en memoire refuse sans rien lever ---------------------


def test_registry_refuses_an_empty_token_or_a_missing_target():
    """Quatre refus d'entree que rien n'essayait.

    Les deux derniers sont arrives avec l'audit de mutation : `register(None)` et
    `artifact_fingerprint(None)` levent tous deux, et personne ne l'essayait. Ils
    sont triviaux a atteindre -- c'est justement ce qui fait qu'on ne les ecrit
    pas -- et le second est la fonction dont depend toute l'identite d'artefact
    du depot, Genesis compris.

    Une precision qui evite de croire ce test plus fort qu'il n'est : le garde de
    `register` est **masque** par celui d'`artifact_fingerprint`, qui leve la
    meme erreur un cran plus bas. Neutraliser le premier ne change donc rien
    d'observable. Cette ligne-la epingle le comportement -- inscrire `None` est
    refuse -- pas ce garde-ci en particulier. Seul celui d'`artifact_fingerprint`
    a un temoin au sens de l'audit.
    """
    import pytest

    from singular.execution_capability import artifact_fingerprint

    registry = ExecutionCapabilityRegistry()
    handler = lambda _action: None
    capability = registry.register(handler, "cap_garde_d_entree")

    assert registry.matches("", handler) is False
    assert registry.matches(capability, None) is False

    with pytest.raises(ValueError, match="execution target is required"):
        registry.register(None, "cap_sans_cible")
    with pytest.raises(ValueError, match="execution target is required"):
        artifact_fingerprint(None)


def test_registry_refuses_an_artifact_whose_fingerprint_moved():
    """Le meme objet, un autre comportement -- et c'est le defaut qui le change.

    `def envoie(action, url="https://banque.example")` et la meme ligne nommant
    un autre hote sont un seul objet code et deux comportements : c'est pour ca
    que l'empreinte couvre les arguments par defaut. Le registre en memoire la
    recompare a chaque appel, et ce refus n'avait pas de temoin -- le meme objet
    suffisait a passer, quel que soit ce qu'il ferait.
    """
    registry = ExecutionCapabilityRegistry()

    def envoie(action, url="https://banque.example"):
        return url

    capability = registry.register(envoie, "cap_empreinte_deplacee")
    assert registry.matches(capability, envoie) is True

    envoie.__defaults__ = ("https://ailleurs.example",)

    assert registry.matches(capability, envoie) is False
