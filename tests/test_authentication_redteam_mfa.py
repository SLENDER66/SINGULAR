from __future__ import annotations

import sqlite3

import pytest
from cryptography.fernet import Fernet

from singular.authentication import AuthenticationError, AuthenticationService, RateLimited, SecondFactorRequired, _totp

PASSWORD = "Correct horse battery staple 2026!"


def service(tmp_path):
    return AuthenticationService(
        tmp_path / "auth.db",
        master_key=Fernet.generate_key(),
        now=lambda: 1_000_000.0,
    )


def test_totp_enrollment_wrong_codes_are_durable_and_throttled(tmp_path):
    auth = service(tmp_path)
    user_id = auth.create_user("user", PASSWORD)
    enrollment = auth.begin_totp_enrollment(user_id, PASSWORD, now=1_000_020.0)

    for _ in range(5):
        with pytest.raises(AuthenticationError):
            auth.confirm_totp_enrollment(user_id, "000000", now=1_000_020.0)

    with pytest.raises(RateLimited):
        auth.confirm_totp_enrollment(user_id, _totp(enrollment.secret, 1_000_020.0), now=1_000_020.0)

    with sqlite3.connect(tmp_path / "auth.db") as conn:
        failures = conn.execute("SELECT failures FROM auth_attempts").fetchall()
    assert failures and max(row[0] for row in failures) >= 5


def test_totp_disable_wrong_codes_are_durable_and_throttled(tmp_path):
    auth = service(tmp_path)
    user_id = auth.create_user("user", PASSWORD)
    enrollment = auth.begin_totp_enrollment(user_id, PASSWORD, now=1_000_020.0)
    auth.confirm_totp_enrollment(user_id, _totp(enrollment.secret, 1_000_020.0), now=1_000_020.0)

    for _ in range(5):
        with pytest.raises(AuthenticationError):
            auth.disable_totp(user_id, PASSWORD, otp="000000")

    with pytest.raises(RateLimited):
        auth.disable_totp(user_id, PASSWORD, otp=_totp(enrollment.secret, 1_000_000.0))


def test_existing_mfa_cannot_be_replaced_with_password_only(tmp_path):
    auth = service(tmp_path)
    user_id = auth.create_user("user", PASSWORD)
    first = auth.begin_totp_enrollment(user_id, PASSWORD, now=1_000_020.0)
    auth.confirm_totp_enrollment(user_id, _totp(first.secret, 1_000_020.0), now=1_000_020.0)

    with pytest.raises(SecondFactorRequired):
        auth.begin_totp_enrollment(user_id, PASSWORD, now=1_000_050.0)

    with pytest.raises(AuthenticationError):
        auth.begin_totp_enrollment(user_id, PASSWORD, otp="000000", now=1_000_050.0)

    second = auth.begin_totp_enrollment(
        user_id,
        PASSWORD,
        otp=_totp(first.secret, 1_000_050.0),
        now=1_000_050.0,
    )
    assert second.secret != first.secret

    # Starting replacement creates only pending state; the old factor remains
    # valid until the replacement is successfully confirmed.
    token = auth.authenticate("user", PASSWORD, otp=_totp(first.secret, 1_000_080.0), now=1_000_080.0)
    assert auth.validate_session(token, now=1_000_080.0).user_id == user_id

    auth.confirm_totp_enrollment(user_id, _totp(second.secret, 1_000_110.0), now=1_000_110.0)
    with pytest.raises(AuthenticationError):
        auth.authenticate("user", PASSWORD, otp=_totp(first.secret, 1_000_140.0), now=1_000_140.0)
    token = auth.authenticate("user", PASSWORD, otp=_totp(second.secret, 1_000_140.0), now=1_000_140.0)
    assert auth.validate_session(token, now=1_000_140.0).user_id == user_id
