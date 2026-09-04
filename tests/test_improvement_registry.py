import pytest

from singular.improvement_registry import ImprovementCandidate, ImprovementEvaluation, ImprovementKind, ImprovementRegistry


def candidate(candidate_id="IMP-1", target="forecast.model"):
    kind = ImprovementKind.MODEL
    hypothesis = "Calibration improves on the evaluated sample."
    evidence = "Historical holdout evaluation."
    return ImprovementCandidate(
        candidate_id=candidate_id,
        kind=kind,
        target=target,
        hypothesis=hypothesis,
        evidence=evidence,
        fingerprint=ImprovementRegistry.candidate_fingerprint(kind=kind, target=target, hypothesis=hypothesis, evidence=evidence),
    )


def evaluation(candidate_id="IMP-1", regression=False, candidate_score=0.9, incumbent_score=0.8, confidence=0.9):
    return ImprovementEvaluation(candidate_id, "v1", "v2", incumbent_score, candidate_score, confidence, regression, "2026-09-04T10:00:00+00:00")


def test_promotion_requires_review_and_evaluation(tmp_path):
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    registry.register(candidate())
    with pytest.raises(PermissionError, match="ACCEPTED"):
        registry.promote("IMP-1")
    registry.review("IMP-1", "ACCEPTED")
    with pytest.raises(PermissionError, match="evaluated"):
        registry.promote("IMP-1")


def test_promotion_requires_non_regression_and_confidence(tmp_path):
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    registry.register(candidate())
    registry.review("IMP-1", "ACCEPTED")
    registry.evaluate(evaluation(regression=True))
    with pytest.raises(PermissionError, match="promotion gates"):
        registry.promote("IMP-1")

    registry.evaluate(evaluation(candidate_score=0.81, incumbent_score=0.8, confidence=0.79))
    with pytest.raises(PermissionError, match="promotion gates"):
        registry.promote("IMP-1")


def test_successful_promotion_is_durable_and_visible_after_restart(tmp_path):
    path = tmp_path / "improvements.db"
    registry = ImprovementRegistry(path)
    registry.register(candidate())
    registry.review("IMP-1", "ACCEPTED")
    registry.evaluate(evaluation())
    activation = registry.promote("IMP-1")
    assert activation.version == "v2"
    assert registry.active("forecast.model") == activation

    restarted = ImprovementRegistry(path)
    assert restarted.active("forecast.model") == activation


def test_safety_critical_policy_cannot_enter_registry(tmp_path):
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    with pytest.raises(PermissionError, match="safety-critical"):
        registry.register(ImprovementCandidate("IMP-SAFE", ImprovementKind.STRATEGY, "policy", "x", "y", "fp", safety_critical=True))


def test_candidate_identity_is_immutable(tmp_path):
    registry = ImprovementRegistry(tmp_path / "improvements.db")
    first = candidate()
    registry.register(first)
    altered = candidate()
    altered = ImprovementCandidate(altered.candidate_id, altered.kind, altered.target, "different", altered.evidence, "different")
    with pytest.raises(ValueError, match="different improvement content"):
        registry.register(altered)
