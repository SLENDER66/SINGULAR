import pytest

from singular.durable import DurableStore, MissionStatus
from singular.learning import Forecast, ForecastKind, LearningEngine
from singular.outcome_ledger import OutcomeLedger
from tests.support import executed_decision
from tests.test_validated_pipeline import _build_decision


def _completed_execution(decision, db_path):
    store = DurableStore(db_path)
    store.save_mission(decision.contract)
    store.set_mission_status(decision.contract.mission_id, MissionStatus.PLANNED)
    key = store.idempotency_key("execute", decision.contract.mission_id, decision.global_report.action_id)
    store.begin_execution_and_start_mission(key, decision.contract.mission_id, decision.global_report.action_id)
    store.finish_execution_and_mission(key, "COMPLETED", result={"ok": True})
    return key


def test_outcome_ledger_records_calibration_against_attested_decision(tmp_path):
    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    execution_key = _completed_execution(decision, tmp_path / "outcomes.db")
    forecast = Forecast("F1", ForecastKind.BINARY, probability=0.8, confidence=0.9)

    record = ledger.record(
        decision=decision,
        forecast=forecast,
        actual=True,
        execution_key=execution_key,
        execution_status="COMPLETED",
    )

    assert record.decision_id == decision.decision_id
    assert record.context_fingerprint == decision.context_fingerprint
    assert record.absolute_error == 0.2
    assert record.brier_score == 0.04
    assert ledger.verify()


def test_outcome_ledger_rejects_unattested_decision(tmp_path):
    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    forecast = Forecast("F1", ForecastKind.BINARY, probability=0.8, confidence=0.9)
    try:
        ledger.record(
            decision=decision,
            forecast=forecast,
            actual=True,
            execution_key="EXEC-1",
            execution_status="COMPLETED",
        )
    except PermissionError as exc:
        # The refusal message is in English here; the test matched a French
        # fragment, so an unattested decision would have satisfied it only by
        # raising some other PermissionError.
        assert "durably issued" in str(exc)
    else:
        raise AssertionError("unattested decision must be rejected")


def test_outcome_ledger_rejects_fake_execution(tmp_path):
    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    forecast = Forecast("F-FAKE", ForecastKind.BINARY, probability=0.8, confidence=0.9)
    key = DurableStore.idempotency_key("execute", decision.contract.mission_id, decision.global_report.action_id)
    try:
        ledger.record(decision=decision, forecast=forecast, actual=True, execution_key=key, execution_status="COMPLETED")
    except PermissionError as exc:
        assert "Aucune exécution durable" in str(exc)
    else:
        raise AssertionError("missing durable execution must be rejected")


def test_numeric_outcomes_preserve_signed_error(tmp_path):
    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    execution_key = _completed_execution(decision, tmp_path / "outcomes.db")
    forecast = Forecast("F2", ForecastKind.NUMERIC, expected_value=10.0, confidence=0.8)

    record = ledger.record(
        decision=decision,
        forecast=forecast,
        actual=13.5,
        execution_key=execution_key,
        execution_status="COMPLETED",
    )

    expected = LearningEngine.evaluate_numeric(forecast, 13.5)
    assert record.absolute_error == expected.error
    assert record.signed_error == 3.5


def test_outcome_ledger_detects_tampering(tmp_path):
    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    execution_key = _completed_execution(decision, tmp_path / "outcomes.db")
    forecast = Forecast("F3", ForecastKind.BINARY, probability=0.2, confidence=0.6)
    ledger.record(
        decision=decision,
        forecast=forecast,
        actual=False,
        execution_key=execution_key,
        execution_status="COMPLETED",
    )
    with ledger._connect() as conn:
        conn.execute("UPDATE outcome_ledger SET actual_value=1 WHERE record_id=(SELECT record_id FROM outcome_ledger LIMIT 1)")
    assert ledger.verify() is False


def test_repeated_identical_observation_is_idempotent(tmp_path):
    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    execution_key = _completed_execution(decision, tmp_path / "outcomes.db")
    forecast = Forecast("F4", ForecastKind.BINARY, probability=0.5, confidence=0.5)
    first = ledger.record(decision=decision, forecast=forecast, actual=True, execution_key=execution_key, execution_status="COMPLETED")
    second = ledger.record(decision=decision, forecast=forecast, actual=True, execution_key=execution_key, execution_status="COMPLETED", observed_at=first.observed_at)
    assert first == second
    assert len(ledger.list()) == 1


def test_recorded_observation_carries_the_forecast_kind_as_an_enum(tmp_path):
    """A str that only compares equal is not the enum consumers test with `is`.

    record() built the observation from a payload holding forecast.kind.value,
    so the object it returned carried "BINARY" rather than ForecastKind.BINARY.
    Every `record.kind is ForecastKind.BINARY` check downstream was False, and a
    binary forecast was scored with the continuous formula -- which is how a
    Brier score of 0.81 produced HOLD with no human review instead of the
    recalibration branch.
    """
    executed = executed_decision(tmp_path / "kinds.db")
    ledger = OutcomeLedger(tmp_path / "kinds.db", attestation_store=executed.engine.attestation_store)
    forecast = Forecast("F-KIND", ForecastKind.BINARY, probability=0.9, confidence=0.9)
    recorded = ledger.record(
        decision=executed.decision,
        forecast=forecast,
        actual=False,
        execution_key=executed.execution_key,
        execution_status=executed.execution_status,
    )

    assert recorded.forecast_kind is ForecastKind.BINARY
    assert ledger.list()[-1].forecast_kind is ForecastKind.BINARY
    assert ledger.verify() is True


def test_a_confident_binary_forecast_that_was_wrong_reaches_recalibration(tmp_path):
    """The consequence the type loss hid, asserted end to end."""
    from singular.learning import CalibrationRecord, LearningEngine
    from singular.learning_strategy import LearningStrategyEngine, StrategyDisposition

    executed = executed_decision(tmp_path / "recalibrate.db")
    ledger = OutcomeLedger(tmp_path / "recalibrate.db", attestation_store=executed.engine.attestation_store)
    forecast = Forecast("F-MISS", ForecastKind.BINARY, probability=0.9, confidence=0.95)
    outcome = ledger.record(
        decision=executed.decision,
        forecast=forecast,
        actual=False,
        execution_key=executed.execution_key,
        execution_status=executed.execution_status,
    )
    assert outcome.brier_score >= 0.25

    record = CalibrationRecord(
        forecast_id=outcome.forecast_id,
        kind=outcome.forecast_kind,
        outcome=outcome.actual_value,
        error=outcome.absolute_error,
        brier_score=outcome.brier_score,
        forecast_confidence=outcome.forecast_confidence,
        lesson=outcome.lesson,
    )
    strategy = LearningStrategyEngine.propose(record, LearningEngine.propose_update(record))
    assert strategy.disposition is StrategyDisposition.TEST
    assert strategy.human_review_required is True


def test_concurrent_records_keep_one_unbroken_chain(tmp_path):
    """Two writers reading the same tail would each link to it, and verify() walks in order.

    A fork needs no tampering to appear and cannot be repaired afterwards: the
    ledger is append-only, so an honest race would leave it permanently
    unverifiable.
    """
    import threading

    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    execution_key = _completed_execution(decision, tmp_path / "outcomes.db")
    errors: list[Exception] = []
    barrier = threading.Barrier(6)

    def record(index: int) -> None:
        try:
            barrier.wait(timeout=10)
            ledger.record(
                decision=decision,
                forecast=Forecast(f"F{index}", ForecastKind.BINARY, probability=0.8, confidence=0.9),
                actual=True,
                execution_key=execution_key,
                execution_status="COMPLETED",
            )
        except Exception as exc:  # noqa: BLE001 - reported through the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=record, args=(index,)) for index in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert len(ledger.list()) == 6
    assert ledger.verify()


# --- la chaine du grand livre, que rien ne verifiait ---------------------------
#
# `verify()` refuse trois choses et deux n'avaient aucun temoin -- la mutation sur
# ce module, mesuree contre la suite entiere, l'a nomme. Ce sont celles qui
# tiennent la chaine : un enregistrement dont l'identifiant ne derive pas de ce
# qu'il dit etre, et un maillon qui ne pointe pas sur le precedent.
#
# C'est la propriete pour laquelle ce fichier existe : un resultat attache apres
# coup a une autre decision, ou une ligne deplacee dans l'ordre, nourrirait la
# calibration avec un fait qui n'a jamais eu lieu sous cette forme. Le journal a la
# meme propriete et elle y est testee depuis toujours ; ici, non.

def _un_enregistrement(tmp_path, forecast_id="F1"):
    from singular.learning import Forecast, ForecastKind

    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    execution_key = _completed_execution(decision, tmp_path / "outcomes.db")
    ledger.record(
        decision=decision,
        forecast=Forecast(forecast_id, ForecastKind.BINARY, probability=0.8, confidence=0.9),
        actual=True,
        execution_key=execution_key,
        execution_status="COMPLETED",
    )
    assert ledger.verify() is True
    return ledger


def test_un_maillon_qui_ne_pointe_plus_sur_le_precedent_ne_se_verifie_pas(tmp_path):
    """Le chainage, casse en SQL comme le ferait n'importe quel acces direct."""
    ledger = _un_enregistrement(tmp_path)

    with ledger._connect() as conn:
        conn.execute("UPDATE outcome_ledger SET previous_fingerprint='autre chose'")

    assert ledger.verify() is False


def test_un_enregistrement_renomme_ne_se_verifie_pas(tmp_path):
    """L'identifiant derive de la decision, de l'execution et de la prevision.

    Le renommer -- ou attacher ce resultat a une autre decision en ne changeant
    que l'identifiant -- doit rompre la verification, sinon la calibration
    apprendrait d'un fait attribue a autre chose.
    """
    ledger = _un_enregistrement(tmp_path)

    with ledger._connect() as conn:
        conn.execute("UPDATE outcome_ledger SET record_id='REC-INVENTE'")

    assert ledger.verify() is False


def test_une_ligne_illisible_ne_se_verifie_pas(tmp_path):
    """Le troisieme refus : ce qui ne se relit meme pas.

    Un genre de prevision que l'enum ne connait pas rend `_row` incapable de
    reconstruire l'observation. `verify()` doit rendre faux -- pas lever, parce que
    son appelant est un affichage : la Notice demande « la chaine tient-elle ? » et
    doit recevoir oui ou non.
    """
    ledger = _un_enregistrement(tmp_path)

    with ledger._connect() as conn:
        conn.execute("UPDATE outcome_ledger SET forecast_kind='CHOSE'")

    assert ledger.verify() is False


# Un refus de `record` reste sans temoin et le restera : la moitie
# `not decision.verify(...)` a cote de `not verify_issuance(...)`. Les deux sont
# co-extensives, et c'est mesure -- `verify_issuance` recalcule l'empreinte depuis
# les champs de la decision, donc tout ce qui fait tomber `verify()` la fait tomber
# aussi. Une decision alteree rend les deux faux dans le meme mouvement ; aucune
# entree ne les distingue. Assurance, pas trou.


# --- a quelle execution un resultat a le droit de se rattacher ------------------
#
# `_validate_execution_observation` refuse cinq choses et aucune n'avait de temoin
# -- mesure contre la suite entiere. C'est la provenance du grand livre : sans ces
# refus, un appelant attache un resultat reel a une autre execution, ou invente un
# statut terminal, et la calibration apprend d'un fait qui n'a pas eu lieu.

def _decision_attestee(tmp_path):
    """Une decision attestee, sans execution : chaque test cree la sienne."""
    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    return decision, ledger


def _forecast(forecast_id="F1"):
    from singular.learning import Forecast, ForecastKind

    return Forecast(forecast_id, ForecastKind.BINARY, probability=0.8, confidence=0.9)


def test_une_cle_d_execution_qui_n_est_pas_celle_de_la_decision_est_refusee(tmp_path):
    """La cle derive de la mission et de l'action : une autre cle est un autre fait."""
    decision, ledger = _decision_attestee(tmp_path)
    _completed_execution(decision, tmp_path / "outcomes.db")

    with pytest.raises(PermissionError, match="clé d'exécution"):
        ledger.record(decision=decision, forecast=_forecast(), actual=True,
                      execution_key="execute-quelque-chose-d-autre", execution_status="COMPLETED")


@pytest.mark.parametrize("champ", ["mission_id", "action_id"])
def test_une_execution_qui_nomme_autre_chose_que_la_decision_est_refusee(tmp_path, champ):
    """La ligne durable est l'autorite, et les deux champs sont lus.

    La cle derive de la mission et de l'action, donc une ligne legitime les porte
    forcement : ce refus garde une base touchee a la main. Sans lui, la cle seule
    suffirait -- et c'est exactement ce que ce module refuse de croire.

    La mission est contrainte par une cle etrangere, donc l'autre mission existe
    vraiment : c'est aussi le cas le plus realiste, deux missions dans la meme base.
    """
    from singular.autopilot import Autonomy, DelegationContract
    from singular.durable import DurableStore

    decision, ledger = _decision_attestee(tmp_path)
    key = _completed_execution(decision, tmp_path / "outcomes.db")
    store = DurableStore(tmp_path / "outcomes.db")
    store.save_mission(DelegationContract("MIS-AUTRE", "autre objectif", "autre résultat",
                                          autonomy=Autonomy.EXECUTE_REVERSIBLE))
    with store._connect() as conn:
        conn.execute(
            f"UPDATE executions SET {champ}=? WHERE execution_key=?",
            ("MIS-AUTRE" if champ == "mission_id" else "ACT-AUTRE", key),
        )

    with pytest.raises(PermissionError, match="n'est pas liée à la mission"):
        ledger.record(decision=decision, forecast=_forecast(), actual=True,
                      execution_key=key, execution_status="COMPLETED")


def test_un_statut_annonce_qui_ne_correspond_pas_au_durable_est_refuse(tmp_path):
    """Le cas le plus banal : un appelant qui sait mal. L'execution a echoue."""
    decision, ledger = _decision_attestee(tmp_path)
    key = _completed_execution(decision, tmp_path / "outcomes.db")

    with pytest.raises(ValueError, match="statut observé ne correspond pas"):
        ledger.record(decision=decision, forecast=_forecast(), actual=True,
                      execution_key=key, execution_status="FAILED")


def test_une_execution_en_cours_ne_nourrit_pas_le_grand_livre(tmp_path):
    """RUNNING n'est pas un resultat, meme annonce fidelement.

    Les deux valeurs correspondent ici -- la ligne durable dit RUNNING et
    l'appelant aussi -- donc c'est bien le refus des etats non terminaux qui doit
    parler. Une reprise en cours n'est pas un fait : le mandat le dit,
    l'ambiguite se resout en demandant au fournisseur, pas en apprenant d'elle.
    """
    from singular.durable import DurableStore, MissionStatus

    decision, ledger = _decision_attestee(tmp_path)
    store = DurableStore(tmp_path / "outcomes.db")
    store.save_mission(decision.contract)
    store.set_mission_status(decision.contract.mission_id, MissionStatus.PLANNED)
    key = store.idempotency_key("execute", decision.contract.mission_id,
                                decision.global_report.action_id)
    store.begin_execution_and_start_mission(key, decision.contract.mission_id,
                                            decision.global_report.action_id)

    with pytest.raises(ValueError, match="exécutions terminales"):
        ledger.record(decision=decision, forecast=_forecast(), actual=True,
                      execution_key=key, execution_status="RUNNING")


@pytest.mark.parametrize("cle, statut", [("", "COMPLETED"), ("   ", "COMPLETED"),
                                         ("execute-x", ""), ("execute-x", "  ")])
def test_une_cle_ou_un_statut_vide_est_refuse_avant_tout(tmp_path, cle, statut):
    """Le premier refus de `record`, avant meme de regarder la decision."""
    decision, ledger = _decision_attestee(tmp_path)

    with pytest.raises(ValueError, match="execution key and status are required"):
        ledger.record(decision=decision, forecast=_forecast(), actual=True,
                      execution_key=cle, execution_status=statut)


def test_un_resultat_binaire_doit_etre_un_booleen(tmp_path):
    """1 n'est pas True ici : l'ecart et le Brier d'une prevision binaire se
    calculent sur un fait arrive ou non, pas sur un nombre."""
    decision, ledger = _decision_attestee(tmp_path)
    key = _completed_execution(decision, tmp_path / "outcomes.db")

    with pytest.raises(TypeError, match="binary forecast outcomes must be bool"):
        ledger.record(decision=decision, forecast=_forecast(), actual=1,
                      execution_key=key, execution_status="COMPLETED")


@pytest.mark.parametrize("actual", [True, False, float("nan"), float("inf")])
def test_un_resultat_numerique_doit_etre_un_nombre_fini(tmp_path, actual):
    """Un booleen et un NaN passeraient tous les deux `float()`.

    Le premier ferait une prevision numerique evaluee sur 1.0 ; le second
    contaminerait toute moyenne qui le croise, sans jamais lever.
    """
    from singular.learning import Forecast, ForecastKind

    decision, ledger = _decision_attestee(tmp_path)
    key = _completed_execution(decision, tmp_path / "outcomes.db")
    numerique = Forecast("F-NUM", ForecastKind.NUMERIC, expected_value=10.0, confidence=0.9)

    with pytest.raises(ValueError, match="numeric forecast outcomes must be finite"):
        ledger.record(decision=decision, forecast=numerique, actual=actual,
                      execution_key=key, execution_status="COMPLETED")


def test_le_meme_resultat_deux_fois_est_idempotent(tmp_path):
    """Deux appels identiques ne font pas deux faits."""
    decision, ledger = _decision_attestee(tmp_path)
    key = _completed_execution(decision, tmp_path / "outcomes.db")
    champs = {"decision": decision, "forecast": _forecast(), "actual": True,
              "execution_key": key, "execution_status": "COMPLETED"}

    premier = ledger.record(**champs)
    second = ledger.record(**champs)

    assert premier == second
    assert len(ledger.list()) == 1
    assert ledger.verify() is True


def test_le_meme_resultat_avec_un_autre_contenu_est_refuse(tmp_path):
    """Le meme fait ne peut pas avoir deux issues, et c'est la promesse du journal
    reprise ici : l'histoire ne se reecrit pas.

    L'identifiant derive de la decision, de l'execution et de la prevision -- donc
    rejouer avec un autre resultat tombe sur le meme identifiant. Sans ce refus,
    le second appel ecraserait le premier ou en ajouterait un second sous le meme
    nom, et la calibration compterait deux fois ce qui est arrive une.
    """
    decision, ledger = _decision_attestee(tmp_path)
    key = _completed_execution(decision, tmp_path / "outcomes.db")
    champs = {"decision": decision, "forecast": _forecast(), "execution_key": key,
              "execution_status": "COMPLETED"}

    ledger.record(actual=True, **champs)

    with pytest.raises(ValueError, match="already exists with different observed content"):
        ledger.record(actual=False, **champs)
    assert len(ledger.list()) == 1
    assert ledger.verify() is True
