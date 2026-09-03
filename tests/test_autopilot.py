from singular.autopilot import *


def test_low_risk_authorized_action_executes():
    mm = MissionManager()
    c = mm.create_contract("Organiser une recherche", "Rapport prêt", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    a = ActionRequest("collect_data", "Collecter des données publiques", 5, 1, 9)
    d = mm.route(a, c.mission_id)
    assert d.mode == Autonomy.EXECUTE_REVERSIBLE
    assert not mm.bus.pending()


def test_sensitive_action_escalates():
    mm = MissionManager()
    c = mm.create_contract("Gérer une mission", "Résultat", autonomy=Autonomy.EXECUTE_AUTHORIZED)
    a = ActionRequest("send_sensitive_message", "Envoyer un message sensible", 8, 3, 8, sensitive=True)
    d = mm.route(a, c.mission_id)
    assert d.mode == Autonomy.ESCALATE
    assert len(mm.bus.pending()) == 1


def test_forbidden_action_blocks():
    mm = MissionManager()
    c = mm.create_contract("Mission", "Résultat", autonomy=Autonomy.EXECUTE_AUTHORIZED, forbidden_actions=("delete_account",))
    a = ActionRequest("delete_account", "Supprimer un compte", 9, 9, 1)
    d = mm.route(a, c.mission_id)
    assert d.mode == Autonomy.BLOCK
    assert not mm.bus.pending()


def test_no_contract_never_autonomously_executes():
    mm = MissionManager()
    a = ActionRequest("generic_action", "Action sans contrat", 4, 1, 9)
    d = mm.route(a)
    assert d.mode == Autonomy.PREPARE


def test_mismatched_action_contract_cannot_borrow_authority():
    mm = MissionManager()
    c = mm.create_contract("Mission A", "Résultat A", autonomy=Autonomy.EXECUTE_AUTHORIZED)
    a = ActionRequest("collect_data", "Collecter des données", 3, 1, 9, contract_id="MIS-FORGED")
    d = mm.route(a, c.mission_id)
    assert d.mode == Autonomy.BLOCK


def test_unknown_mission_fails_closed():
    mm = MissionManager()
    a = ActionRequest("collect_data", "Collecter des données", 3, 1, 9)
    d = mm.route(a, "MIS-UNKNOWN")
    assert d.mode == Autonomy.BLOCK


def test_unknown_approval_cannot_be_approved_or_rejected():
    mm = MissionManager()
    for operation in (mm.bus.approve, mm.bus.reject):
        try:
            operation("APR-UNKNOWN")
        except KeyError:
            pass
        else:
            raise AssertionError("unknown approval must fail closed")
