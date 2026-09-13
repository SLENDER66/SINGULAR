from singular.execution_capability import ExecutionCapabilityRegistry


def test_registry_binds_to_exact_object_identity():
    registry = ExecutionCapabilityRegistry()
    first = lambda _action: None
    second = lambda _action: None
    capability = registry.register(first, "cap_exact_object")

    assert registry.matches(capability, first) is True
    assert registry.matches(capability, second) is False


def test_registry_rejects_token_collision_and_supports_revoke():
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
    """Deux refus d'entree que rien n'essayait."""
    registry = ExecutionCapabilityRegistry()
    handler = lambda _action: None
    capability = registry.register(handler, "cap_garde_d_entree")

    assert registry.matches("", handler) is False
    assert registry.matches(capability, None) is False


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
