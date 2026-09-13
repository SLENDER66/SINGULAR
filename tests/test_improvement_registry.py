"""The chain candidate -> artifact -> evaluation -> approval -> activation.

A version string is a label, not an identity. These tests exist to stop the
registry ever attesting to one artifact and activating another under the same
name, and to stop an evaluation being rewritten after a human has read it.
"""
import pytest

from singular.improvement_registry import (
    SCHEMA_VERSION,
    ImprovementCandidate,
    ImprovementEvaluation,
    ImprovementKind,
    ImprovementRegistry,
    artifact_fingerprint,
)

ARTIFACT = {"weights": [0.1, 0.2], "version": "v2"}
OTHER_ARTIFACT = {"weights": [0.9, 0.9], "version": "v2"}


def candidate(candidate_id="IMP-1", target="forecast.model", artifact=ARTIFACT):
    kind = ImprovementKind.MODEL
    hypothesis = "Calibration improves on the evaluated sample."
    evidence = "Historical holdout evaluation."
    fingerprint = artifact_fingerprint(artifact)
    return ImprovementCandidate(
        candidate_id=candidate_id,
        kind=kind,
        target=target,
        hypothesis=hypothesis,
        evidence=evidence,
        artifact_fingerprint=fingerprint,
        fingerprint=ImprovementRegistry.candidate_fingerprint(
            kind=kind, target=target, hypothesis=hypothesis, evidence=evidence, artifact_fingerprint=fingerprint
        ),
    )


def evaluation(candidate_id="IMP-1", regression=False, candidate_score=0.9, incumbent_score=0.8,
               confidence=0.9, artifact=ARTIFACT, candidate_version="v2"):
    return ImprovementEvaluation(
        candidate_id, artifact_fingerprint(artifact), "v1", candidate_version,
        incumbent_score, candidate_score, confidence, regression, "2026-09-04T10:00:00+00:00",
    )


def _accepted(registry, evaluation_record=None):
    registry.register(candidate())
    registry.evaluate(evaluation_record or evaluation())
    registry.review("IMP-1", "ACCEPTED")


# --- lifecycle ---------------------------------------------------------------

def test_promotion_requires_evaluation_then_review(tmp_path):
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    registry.register(candidate())
    with pytest.raises(PermissionError, match="ACCEPTED"):
        registry.promote("IMP-1")
    with pytest.raises(PermissionError, match="evaluated before it can be reviewed"):
        registry.review("IMP-1", "ACCEPTED")


#: Les trois façons de ne pas mériter l'activation, dans l'ordre où la porte les
#: lit. Le nom du test qui la couvrait promettait « non_regression_and_confidence »
#: et ne jouait que la régression : les deux autres moitiés du même `or` n'avaient
#: aucun témoin, et la mutation par moitiés l'a nommé. Sans elles, un candidat
#: **moins bon que le sortant** s'activait après une revue ACCEPTED, et un
#: candidat évalué sans confiance aussi. C'est exactement ce que la section 14 du
#: mandat interdit : rien n'est meilleur parce qu'on l'a dit.
PROMOTIONS_REFUSEES = [
    ("régression mesurée", {"regression": True}),
    ("pas meilleur que le sortant", {"candidate_score": 0.8, "incumbent_score": 0.8}),
    ("moins bon que le sortant", {"candidate_score": 0.5, "incumbent_score": 0.8}),
    ("évalué sans confiance", {"confidence": 0.79}),
]


@pytest.mark.parametrize("raison, champs", PROMOTIONS_REFUSEES, ids=[r for r, _ in PROMOTIONS_REFUSEES])
def test_promotion_requires_non_regression_and_confidence(tmp_path, raison, champs):
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    _accepted(registry, evaluation(**champs))

    with pytest.raises(PermissionError, match="promotion gates"):
        registry.promote("IMP-1")
    assert registry.active("forecast.model") is None, (
        f"{raison} : rien ne doit être actif après un refus de promotion")


def test_un_candidat_a_peine_meilleur_et_juste_assez_sur_passe(tmp_path):
    """L'autre bord de la même porte : elle doit laisser passer ce qui mérite.

    Trois refus dans une ligne se prouvent par trois cas qui tombent **et** un cas
    qui passe. Sans lui, un garde durci jusqu'à tout refuser passerait les quatre
    tests ci-dessus -- et c'est la faute que ce dépôt appelle fail-closed inutile :
    plus rien ne s'améliore, et rien ne le dit.
    """
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    _accepted(registry, evaluation(candidate_score=0.81, incumbent_score=0.8, confidence=0.8))

    activation = registry.promote("IMP-1")
    assert activation.version == "v2"
    assert registry.active("forecast.model") == activation


@pytest.mark.parametrize("status", ["", "accepted", "ACCEPTE", "PEUT-ETRE", "OUI"])
def test_une_revue_n_a_que_deux_mots(tmp_path, status):
    """Le vocabulaire de la revue humaine, que personne n'essayait de tromper.

    Le cas reel n'est pas un attaquant, c'est une casse : `accepted` en minuscules
    passe par une interface qui recopie une chaine. Accepte, il ne vaudrait pas
    ACCEPTED a la promotion -- donc un candidat revu resterait bloque sans que
    personne comprenne pourquoi. Refuse ici, la faute se voit tout de suite.
    """
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    registry.register(candidate())
    registry.evaluate(evaluation())

    with pytest.raises(ValueError, match="ACCEPTED or REJECTED"):
        registry.review("IMP-1", status)


def test_successful_promotion_is_durable_and_visible_after_restart(tmp_path):
    path = tmp_path / "improvements.db"
    registry = ImprovementRegistry(path)
    _accepted(registry)
    activation = registry.promote("IMP-1")
    assert activation.version == "v2"
    assert activation.artifact_fingerprint == artifact_fingerprint(ARTIFACT)
    assert registry.active("forecast.model") == activation
    assert ImprovementRegistry(path).active("forecast.model") == activation


# --- safety perimeter --------------------------------------------------------

def test_safety_critical_target_cannot_enter_registry(tmp_path):
    """The candidate never declares its own blast radius; the target decides."""
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    with pytest.raises(PermissionError, match="safety-critical"):
        registry.register(candidate(candidate_id="IMP-SAFE", target="execution.boundary"))


def test_a_candidate_cannot_claim_to_be_harmless(tmp_path):
    """The self-declared flag is gone: claiming safety_critical=False was the bypass."""
    with pytest.raises(TypeError):
        ImprovementCandidate("IMP-SAFE", ImprovementKind.STRATEGY, "policy", "x", "y", "afp", "fp", safety_critical=False)


def test_unknown_namespace_is_refused_rather_than_assumed_adaptive(tmp_path):
    """An unclassified target fails closed: a denylist alone would let it through."""
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    with pytest.raises(PermissionError, match="outside the declared adaptive perimeter"):
        registry.register(candidate(candidate_id="IMP-NEW", target="newly.invented.surface"))


def test_target_classification_ignores_case_and_padding(tmp_path):
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    with pytest.raises(PermissionError, match="safety-critical"):
        registry.register(candidate(candidate_id="IMP-CASE", target="  Execution.Boundary  "))


def test_perimeter_cannot_declare_a_safety_critical_namespace_adaptive(tmp_path):
    with pytest.raises(PermissionError, match="cannot be declared adaptive"):
        ImprovementRegistry(tmp_path / "improvements.db", adaptive_namespaces={"forecast", "security"})


def test_activation_rechecks_the_perimeter_at_time_of_use(tmp_path):
    """A perimeter that tightens after review must block the activation, not follow it."""
    path = tmp_path / "improvements.db"
    wide = ImprovementRegistry(path, adaptive_namespaces={"forecast"})
    _accepted(wide)

    narrowed = ImprovementRegistry(path, adaptive_namespaces={"model"})
    with pytest.raises(PermissionError, match="outside the declared adaptive perimeter"):
        narrowed.promote("IMP-1")
    assert narrowed.active("forecast.model") is None


def test_rollback_also_rechecks_the_perimeter(tmp_path):
    path = tmp_path / "improvements.db"
    registry = ImprovementRegistry(path, adaptive_namespaces={"forecast"})
    _accepted(registry)
    activation = registry.promote("IMP-1")

    narrowed = ImprovementRegistry(path, adaptive_namespaces={"model"})
    with pytest.raises(PermissionError, match="outside the declared adaptive perimeter"):
        narrowed.rollback(
            "forecast.model",
            version=activation.version,
            candidate_id=activation.candidate_id,
            artifact_fingerprint=activation.artifact_fingerprint,
        )


# --- artifact identity -------------------------------------------------------

def test_evaluation_must_cover_the_registered_artifact(tmp_path):
    """Artifact substitution: evaluate one thing, register another."""
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    registry.register(candidate())
    with pytest.raises(PermissionError, match="does not cover the artifact"):
        registry.evaluate(evaluation(artifact=OTHER_ARTIFACT))


def test_same_candidate_id_cannot_change_its_content(tmp_path):
    """Le message compte, et l'ancienne version ne le verifiait pas.

    Elle acceptait « different improvement content **ou** different artifact » :
    les deux refus de `register` vivent l'un sous l'autre, donc retirer le premier
    laissait le second parler et le test passait quand meme. Une alternative dans
    un `match` rend un test aveugle a celui des deux gardes qui a repondu.

    Ici seul le contenu change -- meme artefact, autre hypothese -- donc c'est le
    premier qui doit repondre.
    """
    from dataclasses import replace

    registry = ImprovementRegistry(tmp_path / "improvements.db")
    premier = candidate()
    registry.register(premier)
    autre_contenu = replace(premier, hypothesis="Une autre hypothese, meme artefact.",
                            fingerprint=ImprovementRegistry.candidate_fingerprint(
                                kind=premier.kind, target=premier.target,
                                hypothesis="Une autre hypothese, meme artefact.",
                                evidence=premier.evidence,
                                artifact_fingerprint=premier.artifact_fingerprint))

    with pytest.raises(ValueError, match="different improvement content"):
        registry.register(autre_contenu)


def test_same_candidate_id_cannot_change_artifact(tmp_path):
    """Le second refus, et le seul chemin qui l'atteint vraiment.

    L'empreinte de contenu couvre celle de l'artefact, donc un candidat construit
    normalement ne peut pas garder la premiere en changeant la seconde : ce garde
    n'est atteint que par un candidat **forge**, dont l'empreinte de contenu ne
    couvre plus ses champs. C'est exactement la substitution que ce module existe
    pour arreter -- evaluer un artefact, en activer un autre sous le meme nom.
    """
    from dataclasses import replace

    registry = ImprovementRegistry(tmp_path / "improvements.db")
    premier = candidate()
    registry.register(premier)
    forge = replace(premier, artifact_fingerprint=artifact_fingerprint(OTHER_ARTIFACT))

    with pytest.raises(ValueError, match="different artifact"):
        registry.register(forge)


def test_artifact_fingerprint_is_part_of_candidate_identity(tmp_path):
    first = candidate()
    second = candidate(artifact=OTHER_ARTIFACT)
    assert first.fingerprint != second.fingerprint


def test_activation_names_the_artifact_not_only_the_version(tmp_path):
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    _accepted(registry)
    activation = registry.promote("IMP-1")
    assert activation.artifact_fingerprint == artifact_fingerprint(ARTIFACT)


# --- evaluation tampering ----------------------------------------------------

def test_evaluation_is_immutable_once_recorded(tmp_path):
    """The attack the previous INSERT OR REPLACE allowed."""
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    registry.register(candidate())
    registry.evaluate(evaluation(regression=True))
    with pytest.raises(PermissionError, match="immutable once recorded"):
        registry.evaluate(evaluation(regression=False, candidate_score=1.0, confidence=1.0))


def test_repeating_an_identical_evaluation_is_idempotent(tmp_path):
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    registry.register(candidate())
    first = registry.evaluate(evaluation())
    assert registry.evaluate(evaluation()) == first


def test_evaluation_row_edited_in_place_is_tamper_evident(tmp_path):
    """The row is re-fingerprinted from its own fields, not trusted.

    Comparing the stored fingerprint against the review's would only prove the
    two were written together: anyone editing the row directly leaves the
    fingerprint alone and the review still appears to cover it.
    """
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    _accepted(registry, evaluation(regression=True))
    with registry._connect() as conn:
        conn.execute(
            "UPDATE improvement_evaluations SET regression=0, candidate_score=1.0, confidence=1.0 WHERE candidate_id=?",
            ("IMP-1",),
        )
    with pytest.raises(PermissionError, match="does not match its own fingerprint"):
        registry.promote("IMP-1")
    with pytest.raises(PermissionError, match="does not match its own fingerprint"):
        registry.evaluation_of("IMP-1")


def test_review_is_bound_to_the_evaluation_it_read(tmp_path):
    """Repointing the review at some other evaluation must not promote."""
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    _accepted(registry)
    with registry._connect() as conn:
        conn.execute(
            "UPDATE improvement_reviews SET evaluation_fingerprint=? WHERE candidate_id=?",
            ("0" * 64, "IMP-1"),
        )
    with pytest.raises(PermissionError, match="reviewed evaluation is not the evaluation on record"):
        registry.promote("IMP-1")


def test_promotion_refuses_an_artifact_swapped_after_review(tmp_path):
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    _accepted(registry)
    with registry._connect() as conn:
        conn.execute(
            "UPDATE improvement_candidates SET artifact_fingerprint=? WHERE candidate_id=?",
            (artifact_fingerprint(OTHER_ARTIFACT), "IMP-1"),
        )
    with pytest.raises(PermissionError, match="evaluated artifact is not the artifact registered"):
        registry.promote("IMP-1")


def test_review_is_final(tmp_path):
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    registry.register(candidate())
    registry.evaluate(evaluation())
    registry.review("IMP-1", "REJECTED")
    with pytest.raises(PermissionError, match="final and cannot be changed"):
        registry.review("IMP-1", "ACCEPTED")


# --- rollback ----------------------------------------------------------------

def test_rollback_requires_a_previously_activated_version(tmp_path):
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    _accepted(registry)
    with pytest.raises(PermissionError, match="previously activated"):
        registry.rollback("forecast.model", version="v0", candidate_id="IMP-1", artifact_fingerprint=artifact_fingerprint(ARTIFACT))
    registry.promote("IMP-1")
    rollback = registry.rollback(
        "forecast.model", version="v2", candidate_id="IMP-1", artifact_fingerprint=artifact_fingerprint(ARTIFACT)
    )
    assert registry.active("forecast.model") == rollback


def test_rollback_cannot_reuse_a_version_label_for_another_artifact(tmp_path):
    """Two activations could share a label while running different artifacts."""
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    _accepted(registry)
    registry.promote("IMP-1")
    with pytest.raises(PermissionError, match="previously activated"):
        registry.rollback(
            "forecast.model", version="v2", candidate_id="IMP-1", artifact_fingerprint=artifact_fingerprint(OTHER_ARTIFACT)
        )


# --- persistence -------------------------------------------------------------

def test_schema_version_is_recorded(tmp_path):
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    with registry._connect() as conn:
        assert conn.execute("SELECT version FROM improvement_schema").fetchone()["version"] == SCHEMA_VERSION


def test_a_newer_schema_is_refused_rather_than_read(tmp_path):
    path = tmp_path / "improvements.db"
    registry = ImprovementRegistry(path)
    with registry._connect() as conn:
        conn.execute("UPDATE improvement_schema SET version=?", (SCHEMA_VERSION + 1,))
    with pytest.raises(RuntimeError, match="newer version of SINGULAR"):
        ImprovementRegistry(path)


@pytest.mark.parametrize("version", range(1, SCHEMA_VERSION))
def test_an_older_schema_is_refused_rather_than_migrated_silently(tmp_path, version):
    """L'autre bord du meme garde, et celui que la section 13 du mandat nomme.

    Une base ecrite par une version precedente n'a pas les colonnes que ce code
    lit. `CREATE TABLE IF NOT EXISTS` ne migre rien -- il ne s'execute pas quand la
    table est la -- donc sans ce refus la base d'hier serait ouverte et lue comme
    si elle etait a jour. Seule la version **plus recente** etait essayee.

    Il n'y a pas de migration automatique ici, et c'est assume : le refus doit donc
    le dire, et nommer la version trouvee.
    """
    path = tmp_path / "improvements.db"
    registry = ImprovementRegistry(path)
    with registry._connect() as conn:
        conn.execute("UPDATE improvement_schema SET version=?", (version,))

    with pytest.raises(RuntimeError, match=f"v{version} predates v{SCHEMA_VERSION}"):
        ImprovementRegistry(path)


def test_unversioned_database_with_candidates_is_refused(tmp_path):
    """CREATE TABLE IF NOT EXISTS would have read v1 rows as if they were v2."""
    import sqlite3

    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE improvement_candidates (
            candidate_id TEXT PRIMARY KEY, kind TEXT NOT NULL, target TEXT NOT NULL,
            hypothesis TEXT NOT NULL, evidence TEXT NOT NULL, fingerprint TEXT NOT NULL,
            safety_critical INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
        );
        INSERT INTO improvement_candidates VALUES('OLD','MODEL','t','h','e','fp',0,'2026-01-01T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="no artifact identity"):
        ImprovementRegistry(path)


def test_empty_unversioned_database_is_rebuilt(tmp_path):
    import sqlite3

    path = tmp_path / "empty-legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE improvement_candidates (
            candidate_id TEXT PRIMARY KEY, kind TEXT NOT NULL, target TEXT NOT NULL,
            hypothesis TEXT NOT NULL, evidence TEXT NOT NULL, fingerprint TEXT NOT NULL,
            safety_critical INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

    registry = ImprovementRegistry(path)
    _accepted(registry)
    assert registry.promote("IMP-1").version == "v2"


def test_numeric_inputs_must_be_finite(tmp_path):
    with pytest.raises(ValueError, match="must be finite"):
        evaluation(candidate_score=float("nan"))
    with pytest.raises(ValueError, match="must be finite"):
        evaluation(incumbent_score=float("inf"))
    with pytest.raises(ValueError, match="between 0 and 1"):
        evaluation(confidence=1.5)


# --- what an artifact fingerprint is allowed to be ---------------------------

def test_two_equal_artifacts_have_one_fingerprint():
    """It was json.dumps(default=str): a non-JSON artifact became its address."""
    assert artifact_fingerprint({"weights": [0.1, 0.2]}) == artifact_fingerprint({"weights": [0.1, 0.2]})


def test_types_that_json_would_flatten_stay_distinct():
    fingerprints = {artifact_fingerprint({"x": value}) for value in (1, 1.0, True)}
    assert len(fingerprints) == 3


def test_a_callable_artifact_is_identified_by_its_code():
    """Same name, different behaviour: the evaluated one and the activated one."""
    namespace_a: dict = {"__name__": "singular.strategies"}
    namespace_b: dict = {"__name__": "singular.strategies"}
    exec(compile('def score(x):\n    return "safe"\n', "s.py", "exec"), namespace_a)  # noqa: S102
    exec(compile('def score(x):\n    return "risky"\n', "s.py", "exec"), namespace_b)  # noqa: S102

    assert artifact_fingerprint(namespace_a["score"]) != artifact_fingerprint(namespace_b["score"])
    assert artifact_fingerprint(namespace_a["score"]) == artifact_fingerprint(namespace_a["score"])


def test_an_object_that_cannot_name_itself_is_refused():
    """A fingerprint derived from an address is worse than no fingerprint."""

    class Model:
        def __init__(self, weights):
            self.weights = weights

    with pytest.raises(ValueError, match="must be data, a callable, or declare"):
        artifact_fingerprint(Model([1.0, 2.0]))

    with pytest.raises(ValueError, match="must be data, a callable, or declare"):
        artifact_fingerprint({"model": Model([1.0, 2.0])})


def test_an_object_that_declares_its_identity_is_accepted():
    class Declared:
        def __init__(self, weights):
            self.weights = tuple(weights)

        def artifact_identity(self):
            return {"weights": list(self.weights)}

    assert artifact_fingerprint(Declared([1.0, 2.0])) == artifact_fingerprint(Declared([1.0, 2.0]))
    assert artifact_fingerprint(Declared([1.0, 2.0])) != artifact_fingerprint(Declared([9.0, 9.0]))


# --- ce qu'un candidat et une evaluation doivent etre pour exister --------------
#
# Six refus de construction, aucun essaye -- la premiere passe de mutation sur ce
# module les a tous nommes. Ils sont le contrat de la bibliotheque : un candidat
# sans identite, sans empreinte, ou dont l'artefact n'est pas nommable, ne doit pas
# pouvoir etre construit. Et `_evaluation_from_row` reconstruit une evaluation
# depuis la base : ces refus sont donc aussi la porte de sortie d'une ligne abimee.
#
# L'espace au lieu de la chaine vide n'est pas un detail : c'est ce qui distingue
# `not champ` de `not champ.strip()`.

@pytest.mark.parametrize("blanc", ["", "   "])
@pytest.mark.parametrize("champ", ["candidate_id", "target", "hypothesis"])
def test_un_candidat_sans_identite_ne_se_construit_pas(champ, blanc):
    from dataclasses import replace

    with pytest.raises(ValueError, match="identity and hypothesis are required"):
        replace(candidate(), **{champ: blanc})


@pytest.mark.parametrize("champ, message", [
    ("fingerprint", "candidate fingerprint is required"),
    ("artifact_fingerprint", "candidate artifact fingerprint is required"),
])
def test_un_candidat_sans_empreinte_ne_se_construit_pas(champ, message):
    """Les deux empreintes, et elles ne disent pas la meme chose : l'une identifie
    la proposition, l'autre ce qui tournerait."""
    from dataclasses import replace

    with pytest.raises(ValueError, match=message):
        replace(candidate(), **{champ: "  "})


@pytest.mark.parametrize("champ", ["candidate_id", "incumbent_version", "candidate_version"])
def test_une_evaluation_sans_identite_ne_se_construit_pas(champ):
    from dataclasses import replace

    with pytest.raises(ValueError, match="evaluation identity fields are required"):
        replace(evaluation(), **{champ: " "})


def test_une_evaluation_qui_ne_nomme_pas_son_artefact_ne_se_construit_pas():
    """Sans ce refus, la chaine repart d'un label : une evaluation qui ne nomme
    aucun artefact ne peut pas etre comparee a celui du candidat."""
    from dataclasses import replace

    with pytest.raises(ValueError, match="must name the artifact it evaluated"):
        replace(evaluation(), artifact_fingerprint="   ")


@pytest.mark.parametrize("artefact", [
    {1: "un"},
    {"ok": {2: "deux"}},
    {"ok": [{"encore": {None: "rien"}}]},
])
def test_un_artefact_indexe_autrement_que_par_des_chaines_est_refuse(artefact):
    """Le refus vit dans la recursion, pas seulement au sommet.

    Une cle qui n'est pas une chaine ne survit pas au tri (`sorted`) ni au JSON :
    l'empreinte serait soit une erreur, soit deux empreintes pour un artefact. Les
    trois cas descendent d'un niveau a chaque fois, parce qu'un garde ecrit au
    sommet seulement laisserait passer les deux derniers.

    Le `TypeError` interne ressort en `ValueError` : c'est le signal que
    `artifact_fingerprint` utilise pour essayer les deux autres formes d'artefact --
    un appelable, un objet qui se declare -- avant de refuser. Le message du refus
    initial est conserve, et c'est lui qu'on verifie : sans lui, celui qui lit
    l'erreur ne sait pas **quoi** corriger dans son artefact.
    """
    with pytest.raises(ValueError, match="keyed by strings"):
        artifact_fingerprint(artefact)
