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


def test_promotion_requires_non_regression_and_confidence(tmp_path):
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    _accepted(registry, evaluation(regression=True))
    with pytest.raises(PermissionError, match="promotion gates"):
        registry.promote("IMP-1")


def test_successful_promotion_is_durable_and_visible_after_restart(tmp_path):
    path = tmp_path / "improvements.db"
    registry = ImprovementRegistry(path)
    _accepted(registry)
    activation = registry.promote("IMP-1")
    assert activation.version == "v2"
    assert activation.artifact_fingerprint == artifact_fingerprint(ARTIFACT)
    assert registry.active("forecast.model") == activation
    assert ImprovementRegistry(path).active("forecast.model") == activation


def test_safety_critical_policy_cannot_enter_registry(tmp_path):
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    with pytest.raises(PermissionError, match="safety-critical"):
        registry.register(
            ImprovementCandidate("IMP-SAFE", ImprovementKind.STRATEGY, "policy", "x", "y", "afp", "fp", safety_critical=True)
        )


# --- artifact identity -------------------------------------------------------

def test_evaluation_must_cover_the_registered_artifact(tmp_path):
    """Artifact substitution: evaluate one thing, register another."""
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    registry.register(candidate())
    with pytest.raises(PermissionError, match="does not cover the artifact"):
        registry.evaluate(evaluation(artifact=OTHER_ARTIFACT))


def test_same_candidate_id_cannot_change_artifact(tmp_path):
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    registry.register(candidate())
    with pytest.raises(ValueError, match="different improvement content|different artifact"):
        registry.register(candidate(artifact=OTHER_ARTIFACT))


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
