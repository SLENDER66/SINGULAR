"""SINGULAR-native authentication boundary for the future application.

This module authenticates identities; it never grants SINGULAR execution authority.
It uses opaque, revocable database sessions, scrypt password hashes, RFC 6238 TOTP,
and encrypted-at-rest TOTP secrets. Secrets and credentials are deliberately absent
from audit payloads and error messages.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlencode

from cryptography.fernet import Fernet, InvalidToken


PASSWORD_N = 2**15
PASSWORD_R = 8
PASSWORD_P = 1
PASSWORD_MAX_BYTES = 1024
SESSION_TTL_SECONDS = 12 * 60 * 60
TOTP_PERIOD = 30
TOTP_DIGITS = 6
TOTP_SECRET_BYTES = 20
RATE_WINDOW_SECONDS = 15 * 60
RATE_MAX_FAILURES = 5
PENDING_TOTP_TTL_SECONDS = 10 * 60


class AuthenticationError(Exception):
    """Generic authentication failure; intentionally reveals no account state."""


class SecondFactorRequired(AuthenticationError):
    """A valid password was supplied but a second factor is required."""


class RateLimited(AuthenticationError):
    """Authentication attempts are temporarily throttled."""


class SessionInvalid(AuthenticationError):
    """The supplied session is absent, expired, revoked, or stale."""


class AuthenticationConfigurationError(RuntimeError):
    """Production authentication configuration is unsafe or incomplete."""


@dataclass(frozen=True)
class AuthPrincipal:
    user_id: str
    username: str
    security_version: int


@dataclass(frozen=True)
class TotpEnrollment:
    secret: str
    otpauth_uri: str
    expires_at: float


def generate_master_key() -> str:
    """Generate an operator-held Fernet key. Never log or commit the returned value."""
    return Fernet.generate_key().decode("ascii")


def _normalize_login(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("login must be a string")
    value = value.strip().casefold()
    if not value or len(value.encode("utf-8")) > 320:
        raise ValueError("invalid login")
    return value


def _password_bytes(password: str) -> bytes:
    if not isinstance(password, str):
        raise TypeError("password must be a string")
    raw = password.encode("utf-8")
    if not 12 <= len(raw) <= PASSWORD_MAX_BYTES:
        raise ValueError("password must contain 12 to 1024 UTF-8 bytes")
    return raw


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        _password_bytes(password),
        salt=salt,
        n=PASSWORD_N,
        r=PASSWORD_R,
        p=PASSWORD_P,
        maxmem=64 * 1024 * 1024,
    )


def _pack_password(password: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16)
    digest = _password_hash(password, salt)
    return base64.b64encode(salt).decode("ascii"), base64.b64encode(digest).decode("ascii")


def _verify_password(password: str, salt_b64: str, digest_b64: str) -> bool:
    try:
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(digest_b64, validate=True)
        actual = _password_hash(password, salt)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _totp(secret: str, timestamp: float, digits: int = TOTP_DIGITS) -> str:
    normalized = secret.strip().upper()
    padded = normalized + "=" * (-len(normalized) % 8)
    key = base64.b32decode(padded, casefold=True)
    counter = int(timestamp // TOTP_PERIOD)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return f"{value:0{digits}d}"


def _verify_totp(secret: str, code: str, now: float) -> bool:
    if not isinstance(code, str) or len(code) != TOTP_DIGITS or not code.isascii() or not code.isdigit():
        return False
    try:
        return any(hmac.compare_digest(_totp(secret, now + step * TOTP_PERIOD), code) for step in (-1, 0, 1))
    except (ValueError, binascii.Error):  # type: ignore[name-defined]
        return False


def _hash_recovery(code: str, salt: bytes) -> bytes:
    return hashlib.scrypt(code.encode("ascii"), salt=salt, n=2**14, r=8, p=1, maxmem=32 * 1024 * 1024)


def _recovery_record(code: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16)
    digest = _hash_recovery(code, salt)
    return base64.b64encode(salt).decode("ascii"), base64.b64encode(digest).decode("ascii")


def _client_hash(key: str, secret: bytes) -> str:
    return hmac.new(secret, key.encode("utf-8", "strict"), hashlib.sha256).hexdigest()


class AuthenticationService:
    """Durable identity service; authorization remains outside this module."""

    def __init__(self, db_path: str | Path, *, master_key: bytes | str | None = None, now: callable = time.time) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.db_path, 0o600)
        except FileNotFoundError:
            pass
        raw_key = master_key if master_key is not None else os.environ.get("SINGULAR_AUTH_MASTER_KEY")
        if raw_key is None:
            raise AuthenticationConfigurationError("SINGULAR_AUTH_MASTER_KEY is required")
        if isinstance(raw_key, str):
            raw_key = raw_key.encode("ascii")
        try:
            self._fernet = Fernet(raw_key)
        except (ValueError, TypeError):
            raise AuthenticationConfigurationError("invalid authentication master key") from None
        self._rate_secret = hashlib.sha256(raw_key + b"/rate-limit-v1").digest()
        self._now = now
        self._dummy_salt, self._dummy_digest = _pack_password("SINGULAR dummy password 2026!")
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level="IMMEDIATE")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS auth_users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_salt TEXT NOT NULL,
                    password_digest TEXT NOT NULL,
                    security_version INTEGER NOT NULL DEFAULT 1,
                    totp_ciphertext BLOB,
                    totp_pending_ciphertext BLOB,
                    totp_pending_expires REAL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                    expires_at REAL NOT NULL,
                    security_version INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    revoked_at REAL
                );
                CREATE TABLE IF NOT EXISTS auth_recovery_codes (
                    user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                    code_salt TEXT NOT NULL,
                    code_digest TEXT NOT NULL,
                    used_at REAL,
                    PRIMARY KEY(user_id, code_digest)
                );
                CREATE TABLE IF NOT EXISTS auth_attempts (
                    subject_hash TEXT PRIMARY KEY,
                    failures INTEGER NOT NULL,
                    first_failure_at REAL NOT NULL,
                    last_failure_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS auth_sessions_user_idx ON auth_sessions(user_id);
                CREATE INDEX IF NOT EXISTS auth_recovery_user_idx ON auth_recovery_codes(user_id);
                """
            )

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("ascii", "strict")).hexdigest()

    def _record_audit(self, conn: sqlite3.Connection, event: str, user_id: str | None) -> None:
        # Authentication audit intentionally stores identity/event metadata only.
        # Integrators should forward this event to SINGULAR's AuditTrail without credentials.
        conn.execute("CREATE TABLE IF NOT EXISTS auth_audit (event TEXT NOT NULL, user_id TEXT, created_at REAL NOT NULL)")
        conn.execute("INSERT INTO auth_audit(event, user_id, created_at) VALUES (?, ?, ?)", (event, user_id, self._now()))

    def create_user(self, username: str, password: str) -> str:
        login = _normalize_login(username)
        salt, digest = _pack_password(password)
        user_id = "USR-" + secrets.token_hex(16)
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO auth_users(user_id, username, password_salt, password_digest, created_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, login, salt, digest, self._now()),
                )
            except sqlite3.IntegrityError:
                raise ValueError("user already exists") from None
            self._record_audit(conn, "user_created", user_id)
        return user_id

    def begin_totp_enrollment(self, user_id: str, password: str, *, issuer: str = "SINGULAR", now: float | None = None) -> TotpEnrollment:
        current = self._now() if now is None else now
        with self._connect() as conn:
            row = conn.execute("SELECT username, password_salt, password_digest FROM auth_users WHERE user_id=?", (user_id,)).fetchone()
            if row is None or not _verify_password(password, row["password_salt"], row["password_digest"]):
                raise AuthenticationError("authentication failed")
            secret = base64.b32encode(secrets.token_bytes(TOTP_SECRET_BYTES)).decode("ascii").rstrip("=")
            expires = current + PENDING_TOTP_TTL_SECONDS
            cipher = self._fernet.encrypt(secret.encode("ascii"))
            conn.execute("UPDATE auth_users SET totp_pending_ciphertext=?, totp_pending_expires=? WHERE user_id=?", (cipher, expires, user_id))
            self._record_audit(conn, "totp_enrollment_started", user_id)
        label = f"{issuer}:{row['username']}"
        uri = "otpauth://totp/" + quote(label, safe="") + "?" + urlencode({"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": TOTP_DIGITS, "period": TOTP_PERIOD})
        return TotpEnrollment(secret, uri, expires)

    def confirm_totp_enrollment(self, user_id: str, code: str, *, now: float | None = None) -> tuple[str, ...]:
        current = self._now() if now is None else now
        with self._connect() as conn:
            row = conn.execute("SELECT totp_pending_ciphertext, totp_pending_expires FROM auth_users WHERE user_id=?", (user_id,)).fetchone()
            if row is None or row["totp_pending_ciphertext"] is None or row["totp_pending_expires"] is None or current > row["totp_pending_expires"]:
                raise AuthenticationError("authentication failed")
            try:
                secret = self._fernet.decrypt(row["totp_pending_ciphertext"]).decode("ascii")
            except (InvalidToken, UnicodeDecodeError):
                raise AuthenticationConfigurationError("stored authentication secret is invalid") from None
            if not _verify_totp(secret, code, current):
                raise AuthenticationError("authentication failed")
            conn.execute("UPDATE auth_users SET totp_ciphertext=?, totp_pending_ciphertext=NULL, totp_pending_expires=NULL, security_version=security_version+1 WHERE user_id=?", (self._fernet.encrypt(secret.encode("ascii")), user_id))
            conn.execute("DELETE FROM auth_recovery_codes WHERE user_id=?", (user_id,))
            codes: list[str] = []
            for _ in range(10):
                code_value = secrets.token_hex(5).upper()
                salt, digest = _recovery_record(code_value)
                conn.execute("INSERT INTO auth_recovery_codes(user_id, code_salt, code_digest) VALUES (?, ?, ?)", (user_id, salt, digest))
                codes.append(code_value)
            self._revoke_all_sessions(conn, user_id, current)
            self._record_audit(conn, "totp_enabled", user_id)
            return tuple(codes)

    def authenticate(self, login: str, password: str, *, otp: str | None = None, recovery_code: str | None = None, client_key: str = "", now: float | None = None) -> str:
        current = self._now() if now is None else now
        normalized = _normalize_login(login)
        client_hash = _client_hash(client_key, self._rate_secret) if client_key else None
        account_hash = _client_hash(normalized, self._rate_secret)
        with self._connect() as conn:
            if self._rate_limited(conn, account_hash, current) or (client_hash and self._rate_limited(conn, client_hash, current)):
                raise RateLimited("authentication temporarily unavailable")
            row = conn.execute("SELECT * FROM auth_users WHERE username=?", (normalized,)).fetchone()
            password_ok = _verify_password(password, row["password_salt"], row["password_digest"]) if row else _verify_password(password, self._dummy_salt, self._dummy_digest)
            if not password_ok:
                self._record_failure(conn, account_hash, current)
                if client_hash:
                    self._record_failure(conn, client_hash, current)
                raise AuthenticationError("authentication failed")
            if row["totp_ciphertext"] is not None:
                if not otp and not recovery_code:
                    raise SecondFactorRequired("second factor required")
                try:
                    secret = self._fernet.decrypt(row["totp_ciphertext"]).decode("ascii")
                except (InvalidToken, UnicodeDecodeError):
                    raise AuthenticationConfigurationError("stored authentication secret is invalid") from None
                factor_ok = _verify_totp(secret, otp or "", current) if otp else self._consume_recovery(conn, row["user_id"], recovery_code or "", current)
                if not factor_ok:
                    self._record_failure(conn, account_hash, current)
                    if client_hash:
                        self._record_failure(conn, client_hash, current)
                    raise AuthenticationError("authentication failed")
            self._clear_failure(conn, account_hash)
            if client_hash:
                self._clear_failure(conn, client_hash)
            return self._create_session(conn, row["user_id"], row["security_version"], current)

    def validate_session(self, token: str, *, now: float | None = None) -> AuthPrincipal:
        current = self._now() if now is None else now
        if not isinstance(token, str) or len(token) < 32:
            raise SessionInvalid("invalid session")
        token_hash = self._token_hash(token)
        with self._connect() as conn:
            row = conn.execute("SELECT s.*, u.username FROM auth_sessions s JOIN auth_users u ON u.user_id=s.user_id WHERE s.token_hash=?", (token_hash,)).fetchone()
            if row is None or row["revoked_at"] is not None or row["expires_at"] <= current:
                raise SessionInvalid("invalid session")
            user = conn.execute("SELECT security_version FROM auth_users WHERE user_id=?", (row["user_id"],)).fetchone()
            if user is None or user["security_version"] != row["security_version"]:
                raise SessionInvalid("invalid session")
            return AuthPrincipal(row["user_id"], row["username"], row["security_version"])

    def revoke_session(self, token: str) -> None:
        if not isinstance(token, str):
            raise SessionInvalid("invalid session")
        with self._connect() as conn:
            conn.execute("UPDATE auth_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL", (self._now(), self._token_hash(token)))

    def change_password(self, user_id: str, current_password: str, new_password: str) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT password_salt, password_digest FROM auth_users WHERE user_id=?", (user_id,)).fetchone()
            if row is None or not _verify_password(current_password, row["password_salt"], row["password_digest"]):
                raise AuthenticationError("authentication failed")
            salt, digest = _pack_password(new_password)
            conn.execute("UPDATE auth_users SET password_salt=?, password_digest=?, security_version=security_version+1 WHERE user_id=?", (salt, digest, user_id))
            self._revoke_all_sessions(conn, user_id, self._now())
            self._record_audit(conn, "password_changed", user_id)

    def disable_totp(self, user_id: str, password: str, *, otp: str | None = None, recovery_code: str | None = None) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT password_salt, password_digest, totp_ciphertext FROM auth_users WHERE user_id=?", (user_id,)).fetchone()
            if row is None or row["totp_ciphertext"] is None or not _verify_password(password, row["password_salt"], row["password_digest"]):
                raise AuthenticationError("authentication failed")
            try:
                secret = self._fernet.decrypt(row["totp_ciphertext"]).decode("ascii")
            except (InvalidToken, UnicodeDecodeError):
                raise AuthenticationConfigurationError("stored authentication secret is invalid") from None
            ok = _verify_totp(secret, otp or "", self._now()) if otp else self._consume_recovery(conn, user_id, recovery_code or "", self._now())
            if not ok:
                raise AuthenticationError("authentication failed")
            conn.execute("UPDATE auth_users SET totp_ciphertext=NULL, security_version=security_version+1 WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM auth_recovery_codes WHERE user_id=?", (user_id,))
            self._revoke_all_sessions(conn, user_id, self._now())
            self._record_audit(conn, "totp_disabled", user_id)

    def _create_session(self, conn: sqlite3.Connection, user_id: str, security_version: int, now: float) -> str:
        token = secrets.token_urlsafe(32)
        conn.execute("INSERT INTO auth_sessions(token_hash, user_id, expires_at, security_version, created_at) VALUES (?, ?, ?, ?, ?)", (self._token_hash(token), user_id, now + SESSION_TTL_SECONDS, security_version, now))
        self._record_audit(conn, "login_success", user_id)
        return token

    def _revoke_all_sessions(self, conn: sqlite3.Connection, user_id: str, now: float) -> None:
        conn.execute("UPDATE auth_sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now, user_id))

    @staticmethod
    def _rate_limited(conn: sqlite3.Connection, subject_hash: str, now: float) -> bool:
        row = conn.execute("SELECT failures, first_failure_at FROM auth_attempts WHERE subject_hash=?", (subject_hash,)).fetchone()
        if row is None:
            return False
        if now - row["first_failure_at"] >= RATE_WINDOW_SECONDS:
            conn.execute("DELETE FROM auth_attempts WHERE subject_hash=?", (subject_hash,))
            return False
        return row["failures"] >= RATE_MAX_FAILURES

    @staticmethod
    def _record_failure(conn: sqlite3.Connection, subject_hash: str, now: float) -> None:
        row = conn.execute("SELECT failures, first_failure_at FROM auth_attempts WHERE subject_hash=?", (subject_hash,)).fetchone()
        if row is None or now - row["first_failure_at"] >= RATE_WINDOW_SECONDS:
            conn.execute("INSERT OR REPLACE INTO auth_attempts(subject_hash, failures, first_failure_at, last_failure_at) VALUES (?, 1, ?, ?)", (subject_hash, now, now))
        else:
            conn.execute("UPDATE auth_attempts SET failures=failures+1, last_failure_at=? WHERE subject_hash=?", (now, subject_hash))

    @staticmethod
    def _clear_failure(conn: sqlite3.Connection, subject_hash: str) -> None:
        conn.execute("DELETE FROM auth_attempts WHERE subject_hash=?", (subject_hash,))

    @staticmethod
    def _consume_recovery(conn: sqlite3.Connection, user_id: str, code: str, now: float) -> bool:
        if not isinstance(code, str) or len(code) != 10 or not code.isascii() or not code.isalnum():
            return False
        rows = conn.execute("SELECT rowid, code_salt, code_digest FROM auth_recovery_codes WHERE user_id=? AND used_at IS NULL", (user_id,)).fetchall()
        for row in rows:
            try:
                actual = _hash_recovery(code.upper(), base64.b64decode(row["code_salt"], validate=True))
                expected = base64.b64decode(row["code_digest"], validate=True)
            except (ValueError, TypeError):
                continue
            if hmac.compare_digest(actual, expected):
                conn.execute("UPDATE auth_recovery_codes SET used_at=? WHERE rowid=? AND used_at IS NULL", (now, row["rowid"]))
                return conn.total_changes == 1
        return False


__all__ = [
    "AuthPrincipal",
    "AuthenticationConfigurationError",
    "AuthenticationError",
    "AuthenticationService",
    "RateLimited",
    "SecondFactorRequired",
    "SessionInvalid",
    "TotpEnrollment",
    "generate_master_key",
]
