"""What a capability fingerprint must cover: the code, not the shape of the code.

An artifact fingerprint used to hash `co_code` -- the instruction stream -- and
nothing else the code object holds. Instructions address their operands by
index, so the constants a function returns, the globals it calls and the code
objects nested inside it were all reachable only through tables that were never
hashed. Two functions of the same name whose only difference is which URL they
post to compile to byte-identical instructions and were therefore *one
artifact*: after a restart, the second could take over the first's capability
token, satisfy the durable record and satisfy the decision that named it.

That is the substitution the durable capability record exists to refuse, so
these tests are written against that scenario rather than against the digest.
"""
from __future__ import annotations

import functools
from pathlib import Path

import pytest

from singular.execution_capability import (
    SCHEMA_VERSION,
    V1_FINGERPRINT_REVOCATION,
    DurableCapabilityStore,
    ExecutionCapabilityRegistry,
    artifact_fingerprint,
)

#: One module name for every compiled variant below, so module and qualified
#: name are identical and only the body differs -- the impostor's advantage.
PAYMENTS = "singular.providers.payments"


def _compile(body: str, *, name: str = "send", signature: str = "action") -> object:
    source = f"def {name}({signature}):\n{body}\n"
    namespace: dict[str, object] = {"__name__": PAYMENTS}
    exec(compile(source, "payments.py", "exec"), namespace)  # noqa: S102 - the point of the test
    return namespace[name]


def _pays(host: str) -> object:
    return _compile(f'    return post("https://{host}/pay")')


# --- the substitution --------------------------------------------------------

def test_two_payees_behind_one_name_are_not_one_artifact():
    """The scenario in one line: same name, same instructions, different payee."""
    supplier, attacker = _pays("bank.example"), _pays("attacker.example")
    assert supplier.__qualname__ == attacker.__qualname__
    assert supplier.__code__.co_code == attacker.__code__.co_code, "the instructions really are identical"
    assert artifact_fingerprint(supplier) != artifact_fingerprint(attacker)


def test_the_same_implementation_still_fingerprints_the_same():
    """Otherwise a legitimate restart could never re-register anything."""
    assert artifact_fingerprint(_pays("bank.example")) == artifact_fingerprint(_pays("bank.example"))


def test_calling_a_different_global_is_a_different_artifact():
    """`log(action)` and `wire_transfer(action)` differ only in co_names."""
    logs = _compile("    return log(action)")
    wires = _compile("    return wire_transfer(action)")
    assert logs.__code__.co_code == wires.__code__.co_code
    assert artifact_fingerprint(logs) != artifact_fingerprint(wires)


def test_a_default_argument_is_part_of_the_artifact():
    """Defaults are evaluated at definition and live on the function, not the code."""
    to_bank = _compile("    return post(url)", signature='action, url="https://bank.example/pay"')
    to_attacker = _compile("    return post(url)", signature='action, url="https://attacker.example/pay"')
    assert to_bank.__code__ is not to_attacker.__code__
    assert artifact_fingerprint(to_bank) != artifact_fingerprint(to_attacker)


def test_a_keyword_only_default_is_part_of_the_artifact():
    to_bank = _compile("    return post(url)", signature='action, *, url="https://bank.example/pay"')
    to_attacker = _compile("    return post(url)", signature='action, *, url="https://attacker.example/pay"')
    assert artifact_fingerprint(to_bank) != artifact_fingerprint(to_attacker)


def test_code_nested_in_a_constant_is_covered():
    """A comprehension or lambda is a code object stored in co_consts."""
    keeps_a = _compile('    return [item for item in action if item == "a"]')
    keeps_b = _compile('    return [item for item in action if item == "b"]')
    assert artifact_fingerprint(keeps_a) != artifact_fingerprint(keeps_b)


def test_a_provider_class_is_covered_the_same_way():
    """The object path hashes class methods; it hashed their bytecode alone too."""
    def provider(host: str) -> object:
        namespace: dict[str, object] = {"__name__": PAYMENTS}
        exec(  # noqa: S102 - the point of the test
            compile(
                "class Provider:\n"
                "    def execute(self, request, key):\n"
                f'        return post("https://{host}/pay")\n',
                "payments.py",
                "exec",
            ),
            namespace,
        )
        return namespace["Provider"]()

    assert artifact_fingerprint(provider("bank.example")) != artifact_fingerprint(provider("attacker.example"))


def _provider_class(body: str) -> object:
    namespace: dict[str, object] = {
        "__name__": PAYMENTS,
        "functools": functools,
        "pay_supplier": lambda *args: "supplier",
        "pay_attacker": lambda *args: "attacker",
    }
    exec(compile(f"class Provider:\n{body}\n", "payments.py", "exec"), namespace)  # noqa: S102
    return namespace["Provider"]()


def test_a_class_constant_is_covered():
    """Where an endpoint or an account number naturally lives."""
    body = '    ENDPOINT = "https://{host}/pay"\n    def execute(self, request, key):\n        return post(self.ENDPOINT)'
    supplier = _provider_class(body.format(host="bank.example"))
    attacker = _provider_class(body.format(host="attacker.example"))
    assert artifact_fingerprint(supplier) != artifact_fingerprint(attacker)
    assert artifact_fingerprint(supplier) == artifact_fingerprint(_provider_class(body.format(host="bank.example")))


def test_a_property_getter_is_covered():
    """`getattr(cls, name)` on a property yields the property, which has no __code__."""
    body = '    @property\n    def endpoint(self):\n        return "https://{host}/pay"'
    assert artifact_fingerprint(_provider_class(body.format(host="bank.example"))) != artifact_fingerprint(
        _provider_class(body.format(host="attacker.example"))
    )


def test_a_partial_class_member_is_covered():
    """A partial's target and bound arguments are its behaviour."""
    assert artifact_fingerprint(_provider_class("    execute = functools.partial(pay_supplier)")) != artifact_fingerprint(
        _provider_class("    execute = functools.partial(pay_attacker)")
    )
    assert artifact_fingerprint(_provider_class('    execute = functools.partial(pay_supplier, "a")')) != artifact_fingerprint(
        _provider_class('    execute = functools.partial(pay_supplier, "b")')
    )


def test_a_mutable_class_attribute_does_not_move_the_identity():
    """The stated limit on the other side: a cache must not revoke a live capability."""
    provider = _provider_class("    CACHE = {}\n    def execute(self, request, key):\n        return None")
    before = artifact_fingerprint(provider)
    type(provider).CACHE["seen"] = 1
    assert artifact_fingerprint(provider) == before


def test_constants_that_json_would_flatten_stay_distinct():
    """1, True and 1.0 are one value to json; they are three constants here."""
    fingerprints = {artifact_fingerprint(_compile(f"    return {literal}")) for literal in ("1", "True", "1.0")}
    assert len(fingerprints) == 3
    assert artifact_fingerprint(_compile("    return 0.0")) != artifact_fingerprint(_compile("    return -0.0"))


def test_a_constant_that_cannot_be_canonicalised_is_refused_not_ignored(tmp_path: Path):
    """Fail closed: an unfingerprintable constant must not become an empty one.

    The compiler cannot produce such a constant, so reaching this means the code
    object was assembled by hand -- exactly when guessing is worst.
    """
    handler = _pays("bank.example")
    handler.__code__ = handler.__code__.replace(co_consts=(None, object()))

    with pytest.raises(ValueError, match="cannot be fingerprinted"):
        artifact_fingerprint(handler)

    store = DurableCapabilityStore(tmp_path / "capabilities.db")
    store.bind("cap_const", _pays("bank.example"))
    assert store.verify("cap_const", handler) is False


def test_what_a_global_resolves_to_is_a_stated_limit(tmp_path: Path):
    """The boundary of the guarantee, asserted so it cannot quietly move.

    `co_names` records that a function calls `post`; it cannot record which
    `post`. Covering the resolved values would fold live module state into the
    identity -- a module-level counter would revoke the capability while it ran
    -- so a caller who can rewrite a module's globals can change behaviour under
    a stable fingerprint. Rewriting the function object itself, which is the
    easier tampering, is caught.
    """
    source = "def send(action):\n    return post(action)\n"
    supplier: dict[str, object] = {"__name__": PAYMENTS, "post": lambda action: "supplier"}
    attacker: dict[str, object] = {"__name__": PAYMENTS, "post": lambda action: "attacker"}
    exec(compile(source, "payments.py", "exec"), supplier)  # noqa: S102
    exec(compile(source, "payments.py", "exec"), attacker)  # noqa: S102

    assert artifact_fingerprint(supplier["send"]) == artifact_fingerprint(attacker["send"])

    store = DurableCapabilityStore(tmp_path / "capabilities.db")
    store.bind("cap_globals", supplier["send"])
    assert store.verify("cap_globals", attacker["send"]) is True, "covered by neither half; the limit is real"


# --- the restart the durable record exists for -------------------------------

def test_an_impostor_of_the_same_name_cannot_take_over_the_token(tmp_path: Path):
    path = tmp_path / "capabilities.db"
    DurableCapabilityStore(path).bind("cap_pay", _pays("bank.example"))

    restarted = DurableCapabilityStore(path)
    assert restarted.verify("cap_pay", _pays("bank.example")) is True
    assert restarted.verify("cap_pay", _pays("attacker.example")) is False
    with pytest.raises(PermissionError, match="different executable artifact"):
        restarted.bind("cap_pay", _pays("attacker.example"))


def test_a_registry_rebuilt_after_a_restart_refuses_the_impostor(tmp_path: Path):
    """The whole path: fresh in-memory registry, same durable database."""
    path = tmp_path / "capabilities.db"
    ExecutionCapabilityRegistry(DurableCapabilityStore(path)).register(_pays("bank.example"), "cap_pay")

    restarted = ExecutionCapabilityRegistry(DurableCapabilityStore(path))
    with pytest.raises(PermissionError, match="different executable artifact"):
        restarted.register(_pays("attacker.example"), "cap_pay")

    legitimate = _pays("bank.example")
    token = restarted.register(legitimate, "cap_pay")
    assert restarted.matches(token, legitimate) is True
    assert restarted.matches(token, _pays("bank.example")) is False, "in-process, an equal implementation is still another object"


# --- the databases written before this ---------------------------------------

def _write_v1_database(path: Path) -> None:
    """A capability database exactly as schema v1 left it."""
    store = DurableCapabilityStore(path)
    store.bind("cap_legacy", _pays("bank.example"))
    with store._connect() as conn:
        conn.execute("UPDATE execution_capability_schema SET version=1")


def test_a_v1_binding_is_revoked_rather_than_carried_forward(tmp_path: Path):
    """Its fingerprint cannot be recomputed here and cannot be trusted as it is."""
    path = tmp_path / "capabilities.db"
    _write_v1_database(path)

    migrated = DurableCapabilityStore(path)
    record = migrated.get("cap_legacy")
    assert record is not None
    assert record.active is False
    assert record.revoked_reason == V1_FINGERPRINT_REVOCATION
    assert migrated.verify("cap_legacy", _pays("bank.example")) is False


def test_a_v1_token_cannot_be_re_bound_and_says_why(tmp_path: Path):
    """Deleting the rows instead would hand every token to whoever re-binds first."""
    path = tmp_path / "capabilities.db"
    _write_v1_database(path)
    migrated = DurableCapabilityStore(path)

    with pytest.raises(PermissionError, match="rotate to a new capability id"):
        migrated.bind("cap_legacy", _pays("bank.example"))

    rotated = migrated.bind("cap_rotated", _pays("bank.example"))
    assert rotated.active is True


def test_the_migration_runs_once_and_leaves_a_v2_database(tmp_path: Path):
    path = tmp_path / "capabilities.db"
    _write_v1_database(path)
    DurableCapabilityStore(path)

    reopened = DurableCapabilityStore(path)
    with reopened._connect() as conn:
        assert int(conn.execute("SELECT version FROM execution_capability_schema").fetchone()["version"]) == SCHEMA_VERSION
    fresh = reopened.bind("cap_after", _pays("bank.example"))
    assert fresh.active is True

    reopened.revoke("cap_after")
    assert DurableCapabilityStore(path).get("cap_after").active is False


def test_a_schema_from_the_future_is_still_refused(tmp_path: Path):
    path = tmp_path / "capabilities.db"
    store = DurableCapabilityStore(path)
    with store._connect() as conn:
        conn.execute("UPDATE execution_capability_schema SET version=99")
    with pytest.raises(RuntimeError, match="does not match"):
        DurableCapabilityStore(path)


# --- un objet ne peut pas effacer sa propre identite --------------------------

class _FournisseurAutorise:
    """Un fournisseur appelable, comme ceux que la frontiere accepte."""

    def __call__(self, requete):
        return {"ok": True}


class _FournisseurImposteur:
    """Le meme code, une autre classe. Rien ne les distingue que leur nom."""

    def __call__(self, requete):
        return {"ok": True}


def test_un_objet_ne_peut_pas_se_rendre_anonyme_pour_en_imiter_un_autre():
    """L'identite d'un appelable se lit sur sa classe, pas sur ce qu'il declare.

    Un objet peut poser `self.__module__ = ""` et `self.__qualname__ = ""` sur
    lui-meme -- l'affectation tient, `getattr` rend bien la chaine vide. Si
    l'empreinte le croyait, deux classes dont le `__call__` a le meme code
    deviendraient indiscernables : la substitution que la section 12 interdit,
    sous sa forme la plus economique -- pas besoin de reecrire du code, il suffit
    de mentir sur son nom.

    Ce que ce test couvre exactement, et pas davantage : `artifact_fingerprint`
    passe par `_code_identity`, qui lit la classe. Il ne couvre **pas** le repli
    de `_member_identity['callable']`, qui sert aux membres d'une classe -- celui
    du test suivant.
    """
    autorise, imposteur = _FournisseurAutorise(), _FournisseurImposteur()
    assert artifact_fingerprint(autorise) != artifact_fingerprint(imposteur), (
        "deux classes au code identique doivent deja se distinguer")

    for objet in (autorise, imposteur):
        objet.__module__ = ""
        objet.__qualname__ = ""

    assert artifact_fingerprint(autorise) != artifact_fingerprint(imposteur), (
        "un objet qui efface son nom ne doit pas pouvoir en prendre un autre")
    assert artifact_fingerprint(autorise) == artifact_fingerprint(_FournisseurAutorise()), (
        "et effacer son nom ne doit pas non plus changer sa propre empreinte : "
        "un fournisseur legitime cesserait sinon d'etre reconnu par son jeton")


class _AideAutorisee:
    def __call__(self, valeur):
        return valeur


class _AideImposteur:
    def __call__(self, valeur):
        return valeur


def test_un_membre_appelable_est_identifie_par_sa_classe_et_pas_par_ce_qu_il_declare():
    """Le repli de `_member_identity['callable']`, qui sert aux membres.

    Un artefact peut porter, en attribut de classe, un objet appelable -- une
    aide, un adaptateur. `_class_identity` marche sur les membres et confie
    celui-la a `_member_identity`, qui l'identifie par
    `getattr(member, "__module__", "") or owner.__module__` et la meme forme pour
    `__qualname__`.

    Sans ces replis, un membre qui efface son propre nom rendrait deux artefacts
    porteurs d'aides differentes indiscernables : le jeton d'un fournisseur
    accepterait celui d'un autre.
    """
    def fabrique(aide):
        """Deux classes au **meme** nom et dans le meme module.

        C'est ce qui isole le membre : deux classes ecrites cote a cote se
        distinguent deja par leur `__qualname__`, et l'aide qu'elles portent ne
        decide alors de rien. Ici tout est identique sauf elle.
        """
        class Fournisseur:
            pass

        Fournisseur.aide = aide
        return Fournisseur

    autorisee, imposteur = _AideAutorisee(), _AideImposteur()
    porteur, substitue = fabrique(autorisee), fabrique(imposteur)
    assert porteur.__qualname__ == substitue.__qualname__, "le cas n'isole rien sinon"
    assert porteur.__module__ == substitue.__module__
    assert artifact_fingerprint(porteur()) != artifact_fingerprint(substitue()), (
        "l'aide portee doit suffire a distinguer deux artefacts par ailleurs identiques")

    for aide in (autorisee, imposteur):
        aide.__module__ = ""
        aide.__qualname__ = ""

    assert artifact_fingerprint(fabrique(autorisee)()) != artifact_fingerprint(
        fabrique(imposteur)()), (
        "une aide qui efface son propre nom ne doit pas rendre son porteur "
        "indiscernable d'un autre")


def test_deux_aides_du_meme_nom_dans_deux_modules_restent_distinctes():
    """Le repli sur le module, que celui sur le nom masquait.

    Tant que deux aides portent des noms differents, le module ne decide de rien :
    trois des quatre moities de ce repli survivent a toute mutation, parce que le
    nom tranche avant. Elles ne comptent que si les noms sont **identiques** --
    deux classes du meme nom dans deux modules, ce qui est le cas ordinaire d'un
    fournisseur et de son imitation.

    Le cas est monte sans ecrire de fichiers : on donne aux deux classes le meme
    `__qualname__` et deux `__module__` differents. Rien d'autre ne les separe,
    donc c'est le module ou rien.
    """
    class Aide:
        def __call__(self, valeur):
            return valeur

    class AideAilleurs:
        def __call__(self, valeur):
            return valeur

    AideAilleurs.__qualname__ = Aide.__qualname__
    AideAilleurs.__module__ = "un.autre.module"

    def fabrique(aide):
        class Fournisseur:
            pass

        Fournisseur.aide = aide
        return Fournisseur

    ici, ailleurs = Aide(), AideAilleurs()
    for aide in (ici, ailleurs):
        aide.__module__ = ""
        aide.__qualname__ = ""

    assert type(ici).__qualname__ == type(ailleurs).__qualname__, "le cas n'isole rien sinon"
    assert type(ici).__module__ != type(ailleurs).__module__

    assert artifact_fingerprint(fabrique(ici)()) != artifact_fingerprint(
        fabrique(ailleurs)()), (
        "deux aides du meme nom venues de deux modules doivent rester distinctes")


# Ce que ces deux tests laissent, et pourquoi c'est fini plutot qu'a moitie.
#
# `getattr(member, "__x__", "") or owner.__x__` a quatre moities. Les deux
# replis -- `owner.__module__` et `owner.__qualname__` -- sont des gardes, et les
# deux tests ci-dessus les tuent : sans eux, un objet qui efface son nom rend son
# porteur indiscernable d'un autre.
#
# Les deux premieres moities, celles qui lisent ce que l'objet **declare**, ne
# sont pas des gardes et survivront a toute mutation. Les retirer ferait lire
# l'identite sur la seule classe, ce qui est strictement **plus** severe : un
# objet ne pourrait plus se nommer lui-meme. Une mutation qui ne peut que
# resserrer ne peut pas ouvrir de trou, donc il n'y a pas de temoin a ecrire --
# et il ne faut pas en chercher un, c'est ce que cette note evite au passage
# suivant.
