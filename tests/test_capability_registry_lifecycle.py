"""Attaching and revoking must never end somewhere weaker than they started.

`ExecutionCapabilityRegistry` answers "is this the very object registered"; the
durable store answers "is this the artifact the token has always meant". Only
the second survives a restart, so every path that adds or removes it decides
whether the restart substitution is open. Two of them used to fail in the
fail-open direction.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from singular.execution_capability import (
    DurableCapabilityStore,
    ExecutionCapabilityRegistry,
)


def authorized(action):
    return {"executed": True}


def other(action):
    return {"executed": "elsewhere"}


def third(action):
    return {"executed": "third"}


# --- attach ------------------------------------------------------------------

def test_attach_gives_every_held_token_a_durable_meaning(tmp_path: Path):
    registry = ExecutionCapabilityRegistry()
    registry.register(authorized, "cap_a")
    registry.register(other, "cap_b")

    store = DurableCapabilityStore(tmp_path / "capabilities.db")
    registry.attach(store)

    assert store.get("cap_a") is not None
    assert store.get("cap_b") is not None
    assert registry.matches("cap_a", authorized) is True


def test_a_partial_attach_leaves_the_registry_stricter_not_weaker(tmp_path: Path):
    """The failure this test exists for: an attach that raised removed the durable half.

    One token already means another artifact durably, so its bind refuses. The
    registry used to keep no durable store at all, which put every token it held
    back to in-memory verification -- the strongest available answer discarded
    because one binding was wrong.
    """
    path = tmp_path / "capabilities.db"
    store = DurableCapabilityStore(path)
    store.bind("cap_conflict", other)

    registry = ExecutionCapabilityRegistry()
    registry.register(authorized, "cap_conflict")

    with pytest.raises(PermissionError, match="different executable artifact"):
        registry.attach(store)

    assert registry.durable is store, "the durable half must survive the failure"
    assert registry.matches("cap_conflict", authorized) is False


def test_an_unbound_token_stops_matching_after_a_failed_attach(tmp_path: Path):
    """The other half of the same guarantee: tokens the failure never reached."""
    path = tmp_path / "capabilities.db"
    store = DurableCapabilityStore(path)
    store.bind("cap_conflict", other)

    registry = ExecutionCapabilityRegistry()
    # The conflicting token is registered first, and a dict iterates in
    # insertion order, so the attach raises before it reaches this one.
    registry.register(authorized, "cap_conflict")
    registry.register(third, "cap_never_bound")

    with pytest.raises(PermissionError):
        registry.attach(store)

    assert store.get("cap_never_bound") is None, "the loop never reached it"
    assert registry.matches("cap_never_bound", third) is False, "so it must not still match on memory alone"


def test_an_attached_store_cannot_be_replaced(tmp_path: Path):
    """Pointing a registry at a fresh database rewrites what every token means."""
    registry = ExecutionCapabilityRegistry(DurableCapabilityStore(tmp_path / "first.db"))
    registry.register(authorized, "cap_a")

    with pytest.raises(PermissionError, match="cannot be replaced"):
        registry.attach(DurableCapabilityStore(tmp_path / "second.db"))


def test_attaching_the_same_store_twice_is_accepted(tmp_path: Path):
    store = DurableCapabilityStore(tmp_path / "capabilities.db")
    registry = ExecutionCapabilityRegistry(store)
    registry.register(authorized, "cap_a")
    registry.attach(store)
    assert registry.matches("cap_a", authorized) is True


# --- revoke ------------------------------------------------------------------

def test_revocation_reaches_the_durable_store(tmp_path: Path):
    path = tmp_path / "capabilities.db"
    registry = ExecutionCapabilityRegistry(DurableCapabilityStore(path))
    registry.register(authorized, "cap_gone")
    registry.revoke("cap_gone")

    assert DurableCapabilityStore(path).get("cap_gone").active is False


def test_a_durable_write_that_fails_still_kills_the_token_here_and_says_so(tmp_path: Path):
    """A revocation a restart undoes is not a revocation.

    The in-process entry was dropped first and the durable write attempted
    afterwards, so a store that refuses the write left the token dead in this
    process and ACTIVE in the next one. Durable first now, local either way, and
    the caller is told.
    """
    path = tmp_path / "capabilities.db"
    store = DurableCapabilityStore(path)
    registry = ExecutionCapabilityRegistry(store)
    registry.register(authorized, "cap_unwritable")

    def refuse(capability_id: str):
        raise sqlite3.OperationalError("database is locked")

    store.revoke = refuse  # type: ignore[method-assign]

    with pytest.raises(sqlite3.OperationalError):
        registry.revoke("cap_unwritable")

    assert registry.matches("cap_unwritable", authorized) is False, "nothing executes here under it"
    assert DurableCapabilityStore(path).get("cap_unwritable").active is True, "and the caller was told why"


def test_revoking_a_token_never_bound_durably_is_not_an_error(tmp_path: Path):
    registry = ExecutionCapabilityRegistry(DurableCapabilityStore(tmp_path / "capabilities.db"))
    registry._targets["cap_memory_only"] = authorized
    registry.revoke("cap_memory_only")
    assert registry.matches("cap_memory_only", authorized) is False


# --- frapper deux fois le meme objet ------------------------------------------
#
# `register` est idempotent par objet : reenregistrer la meme fonction rend le
# jeton qu'elle a deja. Deux refus vivent dans cette ligne et aucun n'etait
# essaye -- la mutation par moities les a nommes.
#
# Ce n'est pas theorique : `examples/governed_http_effect.py` appelle
# `register_execution_capability(provider)` **sans jeton**. Sans la premiere
# moitie, ce meme appel repete leverait ; sans la seconde, le rappeler avec son
# propre jeton leverait aussi. Et le refus que les deux gardent est reel : un
# objet deja frappe ne peut pas recevoir un second nom, sinon un jeton revoque
# se remplacerait par un jeton neuf pour le meme code.

def test_reenregistrer_le_meme_objet_rend_le_jeton_qu_il_a_deja():
    registry = ExecutionCapabilityRegistry()
    jeton = registry.register(authorized, "cap_idempotence")

    assert registry.register(authorized) == jeton, "sans jeton : celui qu'il a deja"
    assert registry.register(authorized, "cap_idempotence") == jeton, "avec le sien : le meme"


# Un troisieme refus de `register` n'a pas de temoin et n'en aura pas :
# `bound is not target`, quand le jeton demande designe deja cet objet-la. Pour
# l'atteindre il faudrait que les deux tables internes se contredisent -- que
# `_targets[jeton]` soit cet objet alors que `_by_object[id(objet)]` ne dit pas ce
# jeton -- et l'API publique les tient ensemble : `register` ecrit les deux,
# `revoke` retire les deux. Un test peut fabriquer cet etat en ecrivant dans
# `_targets` a la main ; la production, non. Assurance contre un etat interne
# desynchronise, troisieme famille du triage.

def test_un_objet_deja_frappe_ne_recoit_pas_un_second_nom():
    """Le refus que les deux moities gardent, et qui compte : un jeton revoque se

    remplacerait par un jeton neuf pour exactement le meme code.
    """
    registry = ExecutionCapabilityRegistry()
    registry.register(authorized, "cap_premier_nom")

    with pytest.raises(ValueError, match="already bound to a different capability"):
        registry.register(authorized, "cap_second_nom")


# --- ce que le registre refuse de frapper --------------------------------------
#
# Deux refus d'entree de `register`, nommes par la passe complete. Ils gardent le
# cas ou l'appelant se trompe, pas un attaquant -- et ils sont la premiere et la
# troisieme ligne de la fonction, donc ce qui decide si le reste a un sens.

def test_il_faut_un_executable_pour_frapper_un_jeton():
    """`None` n'est pas un executable, et un jeton qui ne designe rien serait pire
    qu'une erreur : `matches` rendrait faux pour toujours sans dire pourquoi."""
    with pytest.raises(ValueError, match="an execution target is required"):
        ExecutionCapabilityRegistry().register(None)


@pytest.mark.parametrize("vide", ["", "   ", "\t"])
def test_un_jeton_vide_est_refuse_avant_le_prefixe(vide):
    """Le refus qui parle du vide, pas celui qui parle du prefixe.

    Les deux se suivent, et le message compte : « capability id cannot be empty »
    dit quoi corriger, la ou « must be an opaque cap_ token » enverrait chercher un
    prefixe sur une chaine qui n'a rien du tout.
    """
    with pytest.raises(ValueError, match="capability id cannot be empty"):
        ExecutionCapabilityRegistry().register(authorized, vide)
