from singular.domain_learning import (
    SENSITIVE_DOMAINS,
    DomainHypothesis,
    DomainLearningResult,
    DomainObservation,
    LearningDisposition,
    LearningDomain,
    UniversalLearningEngine,
)


def test_domains_are_extensible_and_shared_by_one_learning_loop() -> None:
    assert LearningDomain.PSYCHOLOGY.value == "psychology"
    assert LearningDomain.NUTRITION.value == "nutrition"
    assert LearningDomain.FINANCE.value == "finance"
    assert LearningDomain.TECHNOLOGY.value == "technology"


def test_positive_observation_creates_only_an_adoption_proposal() -> None:
    observation = DomainObservation(
        LearningDomain.PRODUCTIVITY, "focused_hours", 4.0, 5.0, 0.9, ("study-1",)
    )
    hypothesis = DomainHypothesis(
        LearningDomain.PRODUCTIVITY,
        "A shorter distraction-free block improves output",
        "Run one protected 90-minute block",
        expected_improvement=1.0,
        evidence_strength=0.9,
    )
    result = UniversalLearningEngine.evaluate(hypothesis, observations=(observation,))
    assert isinstance(result, DomainLearningResult)
    assert result.disposition is LearningDisposition.ADOPT_PROPOSAL
    assert "ADOPTION_REQUIRES_GOVERNANCE" in result.reasons
    assert result.human_review is False


def test_health_adjacent_domains_require_human_review() -> None:
    hypothesis = DomainHypothesis(
        LearningDomain.NUTRITION,
        "This meal pattern may improve consistency",
        "Test a reversible meal-planning change",
        expected_improvement=1.0,
        evidence_strength=0.8,
    )
    result = UniversalLearningEngine.evaluate(hypothesis)
    assert result.disposition is LearningDisposition.TEST
    assert result.human_review is True
    assert "HUMAN_REVIEW_REQUIRED" in result.reasons


def test_high_risk_hypothesis_fails_closed() -> None:
    hypothesis = DomainHypothesis(
        LearningDomain.PSYCHOLOGY,
        "Unknown intervention",
        "Irreversible high-risk intervention",
        expected_improvement=10.0,
        risk=8.0,
        evidence_strength=1.0,
    )
    result = UniversalLearningEngine.evaluate(hypothesis)
    assert result.disposition is LearningDisposition.BLOCK
    assert result.human_review is True


def test_negative_observation_does_not_become_success() -> None:
    observation = DomainObservation(LearningDomain.CAREER, "applications", 10.0, 8.0)
    hypothesis = DomainHypothesis(
        LearningDomain.CAREER,
        "A new approach could improve conversion",
        "Run a bounded test",
        expected_improvement=0.8,
        evidence_strength=0.7,
    )
    result = UniversalLearningEngine.evaluate(hypothesis, observations=(observation,))
    assert "OBSERVED_RESULT_NOT_POSITIVE" in result.reasons
    assert result.disposition is LearningDisposition.REVIEW


def test_improve_evaluates_multiple_domains_as_one_system() -> None:
    observations = (
        DomainObservation(LearningDomain.FINANCE, "monthly_cash", 100.0, 150.0),
        DomainObservation(LearningDomain.KNOWLEDGE, "validated_concepts", 5.0, 7.0),
    )
    hypotheses = (
        DomainHypothesis(LearningDomain.FINANCE, "cash test", "bounded test", 1.0, evidence_strength=0.8),
        DomainHypothesis(LearningDomain.KNOWLEDGE, "learning test", "retrieval practice", 1.0, evidence_strength=0.8),
    )
    results = UniversalLearningEngine.improve(observations, hypotheses)
    assert [item.domain for item in results] == [LearningDomain.FINANCE, LearningDomain.KNOWLEDGE]


def test_sensitive_domains_are_not_a_caller_declaration():
    """A caller may add sensitivity, never remove it.

    human_review used to depend entirely on the `sensitive` argument, so calling
    evaluate() directly on a health-adjacent hypothesis -- the public
    single-hypothesis entry point -- skipped the requirement. Only the batch
    improve() path applied it, and it carried its own copy of the domain set.
    """
    for domain in SENSITIVE_DOMAINS:
        hypothesis = DomainHypothesis(
            domain,
            "A reversible change",
            "Test it",
            expected_improvement=1.0,
            evidence_strength=0.8,
        )
        result = UniversalLearningEngine.evaluate(hypothesis, sensitive=False)
        assert result.human_review is True, f"{domain} must require human review"
        assert "HUMAN_REVIEW_REQUIRED" in result.reasons


def test_non_sensitive_domain_still_does_not_require_review_by_default():
    """The guard must discriminate, not blanket every domain."""
    hypothesis = DomainHypothesis(
        LearningDomain.PRODUCTIVITY,
        "A reversible change",
        "Test it",
        expected_improvement=1.0,
        evidence_strength=0.8,
    )
    assert UniversalLearningEngine.evaluate(hypothesis).human_review is False
    assert UniversalLearningEngine.evaluate(hypothesis, sensitive=True).human_review is True


def test_the_sensitive_domain_set_has_one_definition():
    """Two copies of a safety set drift, and the drift is silent."""
    from singular.human_optimization import HumanOptimizationEngine

    assert HumanOptimizationEngine.SENSITIVE is SENSITIVE_DOMAINS


def test_batch_improve_agrees_with_single_evaluation():
    hypotheses = tuple(
        DomainHypothesis(domain, "A reversible change", "Test it", expected_improvement=1.0, evidence_strength=0.8)
        for domain in (LearningDomain.NUTRITION, LearningDomain.PRODUCTIVITY)
    )
    batch = UniversalLearningEngine.improve((), hypotheses)
    single = tuple(UniversalLearningEngine.evaluate(item) for item in hypotheses)
    assert [item.human_review for item in batch] == [item.human_review for item in single] == [True, False]
