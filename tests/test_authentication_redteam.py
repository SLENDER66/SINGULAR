from __future__ import annotations

import sqlite3

import pytest
from cryptography.fernet import Fernet

from singular.authentication import AuthenticationError, AuthenticationService, RateLimited, _totp


PASSWORD = "Correct horse battery staple 2026!"


def _service(tmp_path):
    return AuthenticationService(
        tmp_path / "auth.db",
        master_key=Fernet.generate_key(),
        now=lambda: 1_000_020.0,
    )


def test_totp_enrollment_repr_never_contains_secret(tmp_path):
    auth = _service(tmp_path)
    user_id = auth.create_user("user", PASSWORD)
    enrollment = auth.begin_totp_enrollment(user_id, PASSWORD)
    rendered = repr(enrollment)
    assert enrollment.secret not in rendered
    assert enrollment.otpauth_uri not in rendered
    assert "secret=" not in rendered


def test_totp_secret_is_not_persisted_in_plaintext_or_audit(tmp_path):
    auth = _service(tmp_path)
    user_id = auth.create_user("user", PASSWORD)
    enrollment = auth.begin_totp_enrollment(user_id, PASSWORD)
    auth.confirm_totp_enrollment(user_id, _totp(enrollment.secret, 1_000_020.0))
    with sqlite3.connect(tmp_path / "auth.db") as conn:
        rows = conn.execute("SELECT totp_ciphertext FROM auth_users").fetchall()
        audit = conn.execute("SELECT event, user_id FROM auth_audit").fetchall()
    assert all(enrollment.secret.encode("ascii") not in row[0] for row in rows)
    assert all(enrollment.secret not in str(row) for row in audit)


def test_totp_secret_is_not_exported_as_public_api(tmp_path):
    auth = _service(tmp_path)
    user_id = auth.create_user("user", PASSWORD)
    enrollment = auth.begin_totp_enrollment(user_id, PASSWORD)
    assert "_totp" not in __import__("singular.authentication", fromlist=["__all__"]).__all__
    assert _totp(enrollment.secret, 1_000_020.0).isdigit()


def test_totp_failures_are_durable_and_rate_limited(tmp_path):
    auth = _service(tmp_path)
    user_id = auth.create_user("user", PASSWORD)
    enrollment = auth.begin_totp_enrollment(user_id, PASSWORD)
    auth.confirm_totp_enrollment(user_id, _totp(enrollment.secret, 1_000_020.0))
    for _ in range(5):
        with pytest.raises(AuthenticationError):
            auth.authenticate("user", PASSWORD, otp="000000", client_key="client-1")
    with pytest.raises(RateLimited):
        auth.authenticate("user", PASSWORD, otp=_totp(enrollment.secret, 1_000_020.0), client_key="client-1")
    with sqlite3.connect(tmp_path / "auth.db") as conn:
        failures = conn.execute("SELECT failures FROM auth_attempts").fetchall()
    assert failures and all(row[0] >= 5 for row in failures)
