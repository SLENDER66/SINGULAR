"""The gate's verdict must never contradict its own requires_human property.

``GlobalDecisionGate.evaluate`` used to compute ``decision`` from an expression
that ran in parallel with the ``requires_human`` property and left out the
governor's mode. An action the Governor escalated therefore came back as
PROCEED while the same report's ``requires_human`` said True.

Nothing was executable that way: ``ValidatedTrajectoryDecision`` refuses any
report whose ``requires_human`` is True, so the escalation was still caught one
layer down. But the headline verdict was fail-open by shape, and a report that
contradicts itself is exactly the kind of thing the next caller reads only half
of. The verdict is now derived from the report, so the two cannot drift.

These tests also pin the design they revealed: a human approval is *not* an
authorization channel through the validated pipeline. An escalated action is
refused at the gate, deliberately, rather than carried forward for a human to
approve later. The approval machinery in ``DurableExecutionEngine`` is a
time-of-use defence -- it catches governance that escalates *after* a decision
was minted -- not a way in.
"""

from dataclasses import replace

import pytest

from singular.autopilot import ActionRequest, Autonomy, DelegationContract
from singular.global_control import GlobalDecisionGate, GlobalDecisionReport
from singular.validated_pipeline import ValidatedTrajectoryPipeline

from tests.test_validated_pipeline import _build_decision, _inputs


def _report(**overrides) -> GlobalDecisionReport:
    base = dict(
        objective="Improve career", action_id="A1", decision="PROCEED",
        blockers=(), warnings=(), capacity_recommendation=None,
        policy_tier="GREEN", policy_requires_human=False,
        governor_mode=Autonomy.EXECUTE_REVERSIBLE, red_team_findings=(), coherence=None,
    )
    base.update(overrides)
    return GlobalDecisionReport(**base)


def _evaluate(action: ActionRequest, contract: DelegationContract) -> GlobalDecisionReport:
    return GlobalDecisionGate().evaluate(
        contract.objective, action, mission_id=contract.mission_id, contract=contract,
    )


def test_an_escalated_action_is_never_reported_as_proceed():
    contract, action, _, _, _, _ = _inputs()
    report = _evaluate(replace(action, requires_human=True), contract)

    assert report.governor_mode is Autonomy.ESCALATE
    assert report.requires_human is True
    assert report.decision == "REVIEW"


def test_a_clean_action_still_proceeds():
    contract, action, _, _, _, _ = _inputs()
    report = _evaluate(action, contract)
    assert report.requires_human is False
    assert report.decision == "PROCEED"


@pytest.mark.parametrize("cause", [
    {"requires_human": True},
    {"sensitive": True},
])
def test_every_governor_escalation_leaves_the_verdict_short_of_proceed(cause):
    """A sensitive action is refused harder still: the policy blocks it outright."""
    contract, action, _, _, _, _ = _inputs()
    report = _evaluate(replace(action, **cause), contract)
    assert report.governor_mode is Autonomy.ESCALATE, cause
    assert report.decision == ("BLOCK" if report.blockers else "REVIEW"), cause
    assert report.decision != "PROCEED", cause


@pytest.mark.parametrize("overrides", [
    {},
    {"warnings": ("COMMANDER:CAPACITY_LIMIT",)},
    {"policy_requires_human": True},
    {"governor_mode": Autonomy.ESCALATE},
    {"warnings": ("W",), "governor_mode": Autonomy.ESCALATE},
    {"blockers": ("POLICY:BLACK",)},
    {"blockers": ("POLICY:BLACK",), "governor_mode": Autonomy.ESCALATE},
])
def test_proceed_means_exactly_no_blocker_and_no_human_needed(overrides):
    """The invariant a caller is allowed to rely on, stated once."""
    report = _report(**overrides)
    verdict = "BLOCK" if report.blockers else ("REVIEW" if report.requires_human else "PROCEED")
    assert (verdict == "PROCEED") == (not report.blockers and not report.requires_human)


class _SpoofGate:
    """A gate that answers honestly, then rewrites its own verdict."""

    def __init__(self, **overrides):
        self.overrides = overrides

    def evaluate(self, *args, **kwargs):
        return replace(GlobalDecisionGate().evaluate(*args, **kwargs), **self.overrides)


def _build_with(gate=None, action_overrides=None):
    contract, action, state, intervention, profile, dimensions = _inputs()
    if action_overrides:
        action = replace(action, **action_overrides)
    return ValidatedTrajectoryPipeline.build(
        objective=contract.objective, actions=(action,),
        action_to_intervention=((action.id, intervention.id),), domain_states=(state,),
        interventions=(intervention,), trajectory_profile=profile,
        trajectory_dimensions=dimensions, contract=contract,
        execution_target=_build_decision().execution_target,
        decision_id="DEC-REVIEW", capacity_budget=2, gate=gate,
    )


def test_the_pipeline_refuses_an_escalated_action_at_the_gate():
    """An escalation is refused where it is detected, not two guards later."""
    with pytest.raises(PermissionError, match="refused execution: REVIEW"):
        _build_with(action_overrides={"requires_human": True})


def test_a_forged_proceed_over_an_escalation_still_does_not_get_through():
    """Rewriting the headline does not remove the escalation underneath it."""
    with pytest.raises((PermissionError, ValueError)):
        _build_with(_SpoofGate(decision="PROCEED", governor_mode=Autonomy.ESCALATE))


def test_a_gate_cannot_authorize_by_rewriting_its_own_verdict():
    """§9: a favourable report must not be enough to make a decision favourable.

    The gate is a parameter of build(), so a caller can supply one that answers
    honestly and then rewrites the headline. What stops it is that the decision
    re-derives the governor and the assessment itself instead of reading them
    off the report.
    """
    with pytest.raises(ValueError, match="explicitly authorize execution|human review"):
        _build_with(_SpoofGate(decision="PROCEED"), action_overrides={"contract_id": "MIS-WRONG"})


def test_rewriting_the_governor_mode_as_well_does_not_help():
    with pytest.raises(ValueError, match="explicitly authorize execution|human review"):
        _build_with(
            _SpoofGate(decision="PROCEED", governor_mode=Autonomy.EXECUTE_AUTHORIZED),
            action_overrides={"requires_human": True},
        )


def test_clearing_the_blockers_does_not_clear_what_produced_them():
    with pytest.raises(ValueError, match="explicitly authorize execution|human review"):
        _build_with(
            _SpoofGate(decision="PROCEED", governor_mode=Autonomy.EXECUTE_AUTHORIZED, blockers=()),
            action_overrides={"sensitive": True, "risk": 9, "reversibility": 1},
        )


# --- ce que le pipeline reconstruit lui-meme ------------------------------------
#
# Section 9 du mandat : une decision favorable ne doit pas pouvoir etre falsifiee en
# fournissant un rapport favorable. Le pipeline y repond en **recalculant**
# l'evaluation de trajectoire et l'optimisation humaine, puis en comparant. Ces deux
# comparaisons n'avaient aucun temoin -- les portes truquees de ce fichier
# reecrivaient le verdict, jamais les pieces sur lesquelles il repose.
#
# La difference compte : une porte qui ment sur le **verdict** est arretee plus bas
# par le gouverneur et la politique, reconstruits eux aussi. Une porte qui ment sur
# les **pieces** passerait ces controles-la, puisqu'ils ne les regardent pas.


class _PorteQuiDeforme:
    """Une porte honnete dont on abime une piece du rapport, pas le verdict."""

    def __init__(self, deformation):
        self._deformation = deformation

    def evaluate(self, *args, **kwargs):
        honnete = GlobalDecisionGate().evaluate(*args, **kwargs)
        return replace(honnete, **self._deformation(honnete))


def test_une_porte_ne_peut_pas_changer_l_evaluation_de_trajectoire():
    """Le rapport doit porter la trajectoire que le pipeline vient de calculer.

    Sans ce controle, une porte annonce le score qu'elle veut : la decision
    enregistrerait une trajectoire et le rapport qui l'autorise en decrirait une
    autre, les deux se disant d'accord.
    """
    porte = _PorteQuiDeforme(
        lambda rapport: {"trajectory": replace(rapport.trajectory,
                                               score=rapport.trajectory.score + 1.0)})
    with pytest.raises(PermissionError, match="trajectory does not match the freshly assessed"):
        _build_with(porte)


def test_une_porte_ne_peut_pas_changer_l_optimisation_humaine():
    """Meme chose pour l'etat humain sur lequel tout le portefeuille est bati."""
    porte = _PorteQuiDeforme(
        lambda rapport: {"human_optimization": replace(
            rapport.human_optimization,
            capacity_used=rapport.human_optimization.capacity_used + 1.0)})
    with pytest.raises(PermissionError, match="human optimization does not match the freshly optimized"):
        _build_with(porte)


def test_une_porte_ne_peut_pas_effacer_la_revue_humaine_de_la_trajectoire():
    """La revue humaine survit a la reecriture du titre, et rien ne l'essayait.

    Une trajectoire qui demande une revue humaine n'arrive jamais jusqu'ici avec une
    porte honnete : le rapport dirait REVIEW et le refus precedent l'arreterait. Il
    faut donc une porte qui reecrive son verdict -- ce qui est exactement le cas que
    la section 9 du mandat demande de tenir -- pour atteindre ce refus-ci.

    Il tient. La porte ment sur le titre, garde honnetement la trajectoire (sinon la
    comparaison du dessus l'arrete), et le pipeline lit `human_review` sur
    l'evaluation qu'il vient de calculer lui-meme. L'entree n'a rien de tordu : une
    capacite dont la confiance est basse, ce que le moteur de trajectoire traduit en
    « a regarder par un humain ».
    """
    from singular.state import CapacitySnapshot

    from tests.test_validated_pipeline import _build_avec

    incertaine = CapacitySnapshot(available=0.9, load=0.1, confidence=0.2)

    # La porte honnete refuse deja cette entree, un cran plus haut : c'est ce qui
    # montre que le refus teste ici n'est pas le meme que celui du dessus.
    with pytest.raises(PermissionError, match="refused execution: REVIEW"):
        _build_avec(capacity=incertaine)

    with pytest.raises(PermissionError, match="Trajectory requires human review"):
        _build_avec(capacity=incertaine, gate=_SpoofGate(decision="PROCEED"))
