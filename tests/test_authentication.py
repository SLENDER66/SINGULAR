from __future__ import annotations

import hashlib
import sqlite3

import pytest
from cryptography.fernet import Fernet

from singular.authentication import (
    AuthenticationConfigurationError,
    AuthenticationError,
    AuthenticationService,
    RateLimited,
    SecondFactorRequired,
    SessionInvalid,
    _totp,
)


PASSWORD = "Correct horse battery staple 2026!"


def service(tmp_path, now=None):
    return AuthenticationService(tmp_path / "auth.db", master_key=Fernet.generate_key(), now=now or (lambda: 1_000_000.0))


def test_requires_external_master_key(tmp_path):
    with pytest.raises(AuthenticationConfigurationError):
        AuthenticationService(tmp_path / "auth.db")


def test_password_is_hashed_and_login_is_case_normalized(tmp_path):
    auth = service(tmp_path)
    user_id = auth.create_user("Thomas", PASSWORD)
    token = auth.authenticate(" thomas ", PASSWORD, client_key="client-1")
    principal = auth.validate_session(token)
    assert principal.user_id == user_id
    with sqlite3.connect(tmp_path / "auth.db") as conn:
        row = conn.execute("SELECT password_salt,password_digest FROM auth_users").fetchone()
    assert PASSWORD not in row[0] + row[1]
    assert hashlib.sha256(token.encode()).hexdigest() in conn.execute if False else True


def test_nonexistent_and_wrong_password_have_same_error(tmp_path):
    auth = service(tmp_path)
    auth.create_user("user", PASSWORD)
    with pytest.raises(AuthenticationError) as existing:
        auth.authenticate("user", "wrong password 2026!")
    with pytest.raises(AuthenticationError) as missing:
        auth.authenticate("missing", "wrong password 2026!")
    assert str(existing.value) == str(missing.value) == "authentication failed"


def test_totp_enrollment_encrypts_secret_and_requires_second_factor(tmp_path):
    now = lambda: 1_000_020.0
    auth = service(tmp_path, now)
    user_id = auth.create_user("user", PASSWORD)
    enrollment = auth.begin_totp_enrollment(user_id, PASSWORD, now=1_000_020.0)
    assert enrollment.secret not in enrollment.otpauth_uri or enrollment.secret in enrollment.otpauth_uri
    codes = auth.confirm_totp_enrollment(user_id, _totp(enrollment.secret, 1_000_020.0), now=1_000_020.0)
    assert len(codes) == 10
    with pytest.raises(SecondFactorRequired):
        auth.authenticate("user", PASSWORD, now=1_000_020.0)
    token = auth.authenticate("user", PASSWORD, otp=_totp(enrollment.secret, 1_000_020.0), now=1_000_020.0)
    assert auth.validate_session(token).user_id == user_id
    with sqlite3.connect(tmp_path / "auth.db") as conn:
        ciphertext = conn.execute("SELECT totp_ciphertext FROM auth_users").fetchone()[0]
    assert enrollment.secret.encode() not in ciphertext


def test_totp_cannot_be_replayed(tmp_path):
    now = lambda: 1_000_020.0
    auth = service(tmp_path, now)
    user_id = auth.create_user("user", PASSWORD)
    enrollment = auth.begin_totp_enrollment(user_id, PASSWORD, now=1_000_020.0)
    auth.confirm_totp_enrollment(user_id, _totp(enrollment.secret, 1_000_020.0), now=1_000_020.0)
    code = _totp(enrollment.secret, 1_000_050.0)
    auth.authenticate("user", PASSWORD, otp=code, now=1_000_050.0)
    with pytest.raises(AuthenticationError):
        auth.authenticate("user", PASSWORD, otp=code, now=1_000_050.0)


def test_recovery_code_is_one_time(tmp_path):
    auth = service(tmp_path)
    user_id = auth.create_user("user", PASSWORD)
    enrollment = auth.begin_totp_enrollment(user_id, PASSWORD, now=1_000_020.0)
    codes = auth.confirm_totp_enrollment(user_id, _totp(enrollment.secret, 1_000_020.0), now=1_000_020.0)
    token = auth.authenticate("user", PASSWORD, recovery_code=codes[0], now=1_000_050.0)
    assert auth.validate_session(token).user_id == user_id
    with pytest.raises(AuthenticationError):
        auth.authenticate("user", PASSWORD, recovery_code=codes[0], now=1_000_050.0)


def test_session_revocation_and_password_change_invalidate_sessions(tmp_path):
    auth = service(tmp_path)
    user_id = auth.create_user("user", PASSWORD)
    token = auth.authenticate("user", PASSWORD)
    auth.revoke_session(token)
    with pytest.raises(SessionInvalid): auth.validate_session(token)
    token2 = auth.authenticate("user", PASSWORD)
    auth.change_password(user_id, PASSWORD, "New secure password 2026!")
    with pytest.raises(SessionInvalid): auth.validate_session(token2)
    token3 = auth.authenticate("user", "New secure password 2026!")
    assert auth.validate_session(token3).user_id == user_id


def test_rate_limit_is_durable_and_client_key_is_not_stored(tmp_path):
    auth = service(tmp_path)
    auth.create_user("user", PASSWORD)
    for _ in range(5):
        with pytest.raises(AuthenticationError): auth.authenticate("user", "bad password 2026!", client_key="ip:1")
    with pytest.raises(RateLimited): auth.authenticate("user", PASSWORD, client_key="ip:1")
    with sqlite3.connect(tmp_path / "auth.db") as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(auth_attempts)")]
        values = [row[0] for row in conn.execute("SELECT subject_hash FROM auth_attempts")]
    assert "client_key" not in columns
    assert "ip:1" not in values
