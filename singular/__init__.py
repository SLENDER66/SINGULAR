"""SINGULAR : le paquet racine, qui ne charge plus rien tant qu'on ne demande rien.

Ce fichier importait cinquante-cinq modules au chargement -- tout le moteur
historique, et `pydantic` avec lui. `python -m singular` en heritait : afficher
un journal exigeait d'installer une dependance que ni le journal, ni la chaine
d'integrite, ni la Notice, ni le Sage n'utilisent. Ils sont en bibliotheque
standard pure, verifie module par module.

La consequence n'etait pas theorique. Elle a repondu a la question « c'est
oblige d'avoir un ordi ? » par oui, alors que la reponse est non : sur un
telephone, ou `pip install` ne passe pas, l'outil devenait injoignable a cause
d'un fichier d'imports, pas a cause de ce qu'il fait.

Les noms exportes sont donc resolus a la demande (PEP 562). `from singular
import X` fonctionne comme avant, et n'importe que ce qu'il faut pour X.

L'ordre des appels a `_depuis` ci-dessous est celui des imports d'hier, et il
compte : plusieurs modules exportent le meme nom -- `Action`, `WorldModel`,
`ActionPolicy` -- et c'est le dernier inscrit qui gagne, comme avant.
`tests/test_lazy_package.py` compare la table a la realite et refuse toute
divergence.
"""
from __future__ import annotations

import importlib
from typing import Any

#: nom expose -> (module, nom d'origine dans ce module).
_EXPORTS: dict[str, tuple[str, str]] = {}


def _depuis(module: str, *noms: str, **renommes: str) -> None:
    for nom in noms:
        _EXPORTS[nom] = (module, nom)
    for expose, origine in renommes.items():
        _EXPORTS[expose] = (module, origine)


def _table() -> None:
    _depuis(
        "models",
        "Action", "Any", "BaseModel", "Certainty", "ConfigDict", "Decision", "Enum",
        "Evidence", "Field", "Learning", "Objective", "Opportunity", "Optional", "Resource",
        "Risk", "Status", "WorldModel", "annotations",
    )
    _depuis("engine", "SingularEngine")
    _depuis("agents", "Commander", "RedTeam", "LearningEngine", "SystemArchitect")
    _depuis(
        "autopilot",
        "ActionClass", "ActionRequest", "ApprovalRequest", "ApprovalStatus", "Autonomy",
        "DelegationContract", "Enum", "ExecutionBus", "Governor", "GovernorDecision",
        "HumanTaskFilter", "MissionManager", "Optional", "annotations", "dataclass", "field",
        "isfinite", "uuid4",
    )
    _depuis(
        "v3_operating_system",
        "Action", "ActionPolicy", "ActionRequest", "Any", "AuditTrail", "Autonomy", "Callable",
        "CandidateAction", "Certainty", "Decision", "DecisionAssessment", "DecisionEngine",
        "DelegationContract", "Enum", "Evidence", "ExecutionBus", "Learning",
        "LearningEngineV3", "LearningRecord", "ObservationCycle", "OperatingSnapshot",
        "PolicyDecision", "Signal", "SignalType", "SingularV3", "SystemArchitectV3",
        "SystemChange", "WorldModel", "WorldModelUpdater", "annotations", "dataclass",
        "datetime", "field", "timezone", "uuid4",
    )
    _depuis("config", "Settings")
    _depuis("security", "ActionPolicy", "ActionTier", "PolicyDecision")
    _depuis("audit", "AuditEvent", "AuditTrail")
    _depuis("health", "HealthStatus", "check_system")
    _depuis("production_runtime", "AgentsSDKRuntime", "RuntimeStatus")
    _depuis(
        "v32_governed_core",
        "GovernedAction", "GovernedExecutor", "GovernedMission", "RedTeamFinding",
        "RedTeamGate", "Specialist", "SpecialistResult", "WorkforcePlan", "WorkforceRouter",
    )
    _depuis("mission_runtime", "DurableMissionRuntime", "MissionState")
    _depuis("durable", "DurableStore", "MissionStatus")
    _depuis(
        "effects",
        "EffectInProgress", "EffectProvider", "EffectRequest", "EffectStatus",
        "ExternalEffectCoordinator", "ProviderResult",
    )
    _depuis("coherence", "CoherenceReport", "GlobalCoherenceGuard")
    _depuis(
        "authority",
        "AgentPower", "AuthorityProfile", "AuthorityProtocol", "ConflictResolution",
        "ConflictType",
    )
    _depuis(
        "world_model",
        "EpistemicType", "OpportunityClass", "TemporalState", "WorldFact", "WorldOpportunity",
    )
    _depuis(
        "values",
        "CoreValue", "ValueAssessment", "ValueAssessmentResult", "ValueMode", "ValuesEngine",
        "Vision",
    )
    _depuis("state", "CapacityEngine", "CapacitySnapshot", "StateDimension", "StateObservation")
    _depuis("global_control", "GlobalDecisionGate", "GlobalDecisionReport")
    _depuis(
        "learning",
        "CalibrationRecord", "Forecast", "ForecastKind", "LearningUpdate",
        CalibrationLearningEngine="LearningEngine",
    )
    _depuis(
        "learning_strategy",
        "LearningStrategyEngine", "StrategyDisposition", "StrategyProposal",
    )
    _depuis(
        "decision_engine",
        "DecisionContext", "DecisionOption", "DecisionRecommendation", "DecisionStatus",
        GovernedDecisionEngine="DecisionEngine",
    )
    _depuis(
        "execution_result",
        "ExecutionIntent", "ExecutionResult", "ExecutionResultBridge", "ExecutionStatus",
    )
    _depuis("durable_execution", "DurableExecutionLedger")
    _depuis("learning_bridge", "ExecutionLearningBridge", "LearningResult")
    _depuis("economic_learning", "EconomicLearningCycle", "EconomicLearningEngine")
    _depuis("economic_learning_ledger", "EconomicLearningLedger")
    _depuis(
        "meta_audit",
        "AgentCalibration", "MetaAuditEngine", "MetaAuditFinding", "MetaAuditReport",
        "MetaAuditSeverity",
    )
    _depuis("provenance", "ProvenanceChain", "ProvenanceRecord")
    _depuis(
        "adversarial",
        "AttackClass", "AdversarialEngine", "AdversarialFinding", "AdversarialReport",
        "AttackSeverity",
    )
    _depuis(
        "collective_intelligence",
        "CollectiveIntelligence", "Deliberation", "KnowledgeKind", "SharedSignal",
    )
    _depuis(
        "trajectory",
        "TrajectoryAssessment", "TrajectoryDecision", "TrajectoryEngine", "TrajectoryProfile",
    )
    _depuis(
        "domain_learning",
        "DomainHypothesis", "DomainLearningResult", "DomainObservation", "LearningDisposition",
        "LearningDomain", "UniversalLearningEngine",
    )
    _depuis(
        "human_optimization",
        "DomainInteraction", "DomainState", "HumanOptimizationReport", "Intervention",
        "OptimizationCandidate", "OptimizationDisposition",
        CanonicalHumanOptimizationEngine="HumanOptimizationEngine",
    )
    _depuis(
        "trajectory_optimization",
        "TrajectoryInteraction", "TrajectoryOptimizationEngine", "TrajectoryPortfolio",
    )
    _depuis(
        "execution_capability",
        "ExecutionCapabilityRegistry", "GLOBAL_EXECUTION_CAPABILITIES",
        "execution_capability_matches", "register_execution_capability",
    )
    _depuis(
        "decision_attestation",
        "DecisionAttestation", "DecisionAttestationStore", "ValidatedDecisionIssuer",
    )
    _depuis(
        "validated_trajectory_decision",
        "ValidatedActionRequest", "ValidatedTrajectoryDecision", "payload_fingerprint",
    )
    _depuis("validated_execution", "ValidatedExecutionBoundary")
    _depuis("validated_pipeline", "ValidatedTrajectoryPipeline")
    _depuis("validated_decision_service", "ValidatedDecisionService")
    _depuis("control_plane", "ControlPlaneDecision", "SingularControlPlane")
    _depuis(
        "history_world_model",
        "EpistemicLevel", "FutureDisposition", "FutureReasoner", "FutureScenario",
        "HistoricalEvidence", "HistoricalMode", "HistoricalPattern", "HistoricalReasoner",
        "TemporalAssessment", "TemporalContext", "WorldStateSnapshot",
        "build_temporal_context",
    )
    _depuis(
        "execution_boundary_audit",
        "BoundaryAuditReport", "BoundaryFinding", "ExecutionBoundaryAuditor",
    )
    _depuis("outcome_ledger", "OutcomeLedger", "OutcomeObservation")
    _depuis("learning_review_queue", "LearningReview", "LearningReviewQueue")
    _depuis("continuous_learning", "ContinuousLearningCycle", "LearningCycleResult")
    _depuis("self_improvement", "SelfImprovementEngine", "SelfImprovementProposal")
    _depuis(
        "improvement_registry",
        "ImprovementActivation", "ImprovementCandidate", "ImprovementEvaluation",
        "ImprovementKind", "ImprovementRegistry", "artifact_fingerprint",
    )
    _depuis("durable_recovery", "confirm_execution_recovery_from_effect")
    _depuis(
        "durable_integrity",
        "DurableIntegrityChecker", "DurableIntegrityReport", "IntegrityViolation",
    )
    _depuis("world_model", EpistemicWorldModel="WorldModel")
    _depuis("providers", "HttpEffectProvider", "HttpProviderError")
    _depuis("journal", "DecisionJournal", JournalTier="Tier")

_table()

#: Le nom historique : `models.WorldModel` reste `WorldModel`. Le modele
#: epistemique est expose sous un nom distinct, volontairement.
_EXPORTS["EpistemicWorldModel"] = ("world_model", "WorldModel")

#: Une liste litterale, pas `sorted(...)` seul : ruff exige de pouvoir lire
#: `__all__` statiquement, et refuse aussi un `list()` autour d'un `sorted()`.
#: Le depaquetage satisfait les deux.
__all__ = [*sorted(_EXPORTS)]  # noqa: PLE0604 -- les cles de _EXPORTS sont des str,
# mais ruff ne peut pas le prouver statiquement a travers le depaquetage.


def __getattr__(nom: str) -> Any:
    """Resolution paresseuse : on n'importe que ce qui est reellement demande."""
    cible = _EXPORTS.get(nom)
    if cible is not None:
        module, origine = cible
        return getattr(importlib.import_module(f".{module}", __name__), origine)
    # `import singular; singular.audit` marchait parce que les imports
    # d'en-tete liaient chaque sous-module comme attribut. Sans ce repli, la
    # paresse casserait cet usage-la en silence.
    try:
        return importlib.import_module(f".{nom}", __name__)
    except ImportError:
        raise AttributeError(f"module {__name__!r} has no attribute {nom!r}") from None


def __dir__() -> list[str]:
    return __all__
