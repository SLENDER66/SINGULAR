from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from singular.authentication import AuthenticationError, AuthenticationService, RateLimited, _subject_hash, _totp

PASSWORD = "Correct horse battery staple 2026!"


def _service(path: Path, key: bytes) -> AuthenticationService:
    return AuthenticationService(path, master_key=key, now=lambda: 1_000_020.0)


def _parallel(callable_, count=2):
    def wrapped():
        try:
            return callable_()
        except Exception as exc:  # test helper intentionally captures expected races
            return exc

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(lambda _: wrapped(), range(count)))


def test_totp_replay_is_single_winner_across_two_service_instances(tmp_path):
    db = tmp_path / "auth.db"
    key = Fernet.generate_key()
    setup = AuthenticationService(db, master_key=key, now=lambda: 1_000_020.0)
    user_id = setup.create_user("user", PASSWORD)
    enrollment = setup.begin_totp_enrollment(user_id, PASSWORD)
    setup.confirm_totp_enrollment(user_id, _totp(enrollment.secret, 1_000_020.0))

    services = [_service(db, key), _service(db, key)]
    login_code = _totp(enrollment.secret, 1_000_050.0)
    results = _parallel(lambda: services.pop().authenticate("user", PASSWORD, otp=login_code))
    successes = [item for item in results if isinstance(item, str)]
    failures = [item for item in results if isinstance(item, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], AuthenticationError)


def test_recovery_replay_is_single_winner_across_two_service_instances(tmp_path):
    db = tmp_path / "auth.db"
    key = Fernet.generate_key()
    setup = AuthenticationService(db, master_key=key, now=lambda: 1_000_020.0)
    user_id = setup.create_user("user", PASSWORD)
    enrollment = setup.begin_totp_enrollment(user_id, PASSWORD)
    codes = setup.confirm_totp_enrollment(user_id, _totp(enrollment.secret, 1_000_020.0))

    services = [_service(db, key), _service(db, key)]
    results = _parallel(lambda: services.pop().authenticate("user", PASSWORD, recovery_code=codes[0]))
    successes = [item for item in results if isinstance(item, str)]
    failures = [item for item in results if isinstance(item, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], AuthenticationError)


def test_concurrent_failed_logins_increment_durable_counter(tmp_path):
    db = tmp_path / "auth.db"
    key = Fernet.generate_key()
    setup = AuthenticationService(db, master_key=key, now=lambda: 1_000_020.0)
    setup.create_user("user", PASSWORD)

    services = [_service(db, key), _service(db, key)]
    results = _parallel(lambda: services.pop().authenticate("user", "wrong password", client_key="client"))
    assert all(isinstance(item, AuthenticationError) for item in results)

    with setup._connect() as conn:
        account_subject = conn.execute(
            "SELECT failures FROM auth_attempts WHERE subject_hash=?",
            (_subject_hash("user", setup._rate_secret),),
        ).fetchone()
    # The account limiter must observe both concurrent failures, rather than
    # losing one update to a read/modify/write race.
    assert account_subject is not None
    assert account_subject["failures"] >= 2


def test_rate_limit_survives_restart(tmp_path):
    db = tmp_path / "auth.db"
    key = Fernet.generate_key()
    auth = AuthenticationService(db, master_key=key, now=lambda: 1_000_020.0)
    auth.create_user("user", PASSWORD)

    for _ in range(5):
        with pytest.raises(AuthenticationError):
            auth.authenticate("user", "wrong password", client_key="client")

    restarted = AuthenticationService(db, master_key=key, now=lambda: 1_000_020.0)
    with pytest.raises(RateLimited):
        restarted.authenticate("user", PASSWORD, client_key="client")
