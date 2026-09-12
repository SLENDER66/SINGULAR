"""Fail-closed authentication boundary for the future SINGULAR application.

Authentication is separate from authorization/governance: a valid principal never
receives an execution capability from this module. Passwords are scrypt hashes,
TOTP secrets are encrypted with an external Fernet key, sessions are opaque and
stored only as hashes, and TOTP/recovery credentials resist replay.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import secrets
import sqlite3
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlencode

from cryptography.fernet import Fernet, InvalidToken

from .sqlite_support import SqliteLocation

PASSWORD_N, PASSWORD_R, PASSWORD_P = 2**15, 8, 1
RECOVERY_N, RECOVERY_R, RECOVERY_P = 2**14, 8, 1
SESSION_TTL = 12 * 60 * 60
TOTP_PERIOD, TOTP_DIGITS = 30, 6
RATE_WINDOW, RATE_LIMIT = 15 * 60, 5
PENDING_TOTP_TTL = 10 * 60


class AuthenticationError(Exception):
    """Generic authentication failure; never reveals account state."""


class SecondFactorRequired(AuthenticationError):
    """Password is valid but a configured second factor is required."""


class RateLimited(AuthenticationError):
    """Authentication attempts are temporarily throttled."""


class SessionInvalid(AuthenticationError):
    """Session is missing, expired, revoked, or stale."""


class AuthenticationConfigurationError(RuntimeError):
    """Authentication cannot safely start with the supplied configuration."""


@dataclass(frozen=True)
class AuthPrincipal:
    user_id: str
    username: str
    security_version: int


@dataclass(frozen=True)
class TotpEnrollment:
    # A TOTP secret is a live authentication credential. It must never appear in
    # the default dataclass repr (logs, tracebacks, debugging, etc.).
    secret: str = field(repr=False)
    otpauth_uri: str = field(repr=False)
    expires_at: float


def generate_master_key() -> str:
    """Generate an operator-held key. Never log or commit the returned value."""
    return Fernet.generate_key().decode("ascii")


def _login(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("login must be a string")
    value = value.strip().casefold()
    if not value or len(value.encode()) > 320:
        raise ValueError("invalid login")
    return value


def _password(value: str) -> bytes:
    if not isinstance(value, str):
        raise TypeError("password must be a string")
    raw = value.encode()
    if not 12 <= len(raw) <= 1024:
        raise ValueError("password must contain 12 to 1024 UTF-8 bytes")
    return raw


def _scrypt(value: bytes, salt: bytes, n: int, r: int, p: int, maxmem: int) -> bytes:
    return hashlib.scrypt(value, salt=salt, n=n, r=r, p=p, maxmem=maxmem)


def _password_record(password: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16)
    digest = _scrypt(_password(password), salt, PASSWORD_N, PASSWORD_R, PASSWORD_P, 64 * 1024 * 1024)
    return base64.b64encode(salt).decode(), base64.b64encode(digest).decode()


def _password_ok(password: str, salt_text: str, digest_text: str) -> bool:
    try:
        salt = base64.b64decode(salt_text, validate=True)
        expected = base64.b64decode(digest_text, validate=True)
        actual = _scrypt(_password(password), salt, PASSWORD_N, PASSWORD_R, PASSWORD_P, 64 * 1024 * 1024)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _totp_parts(secret: str, now: float) -> tuple[str, int]:
    padded = secret.upper() + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded, casefold=True)
    counter = int(now // TOTP_PERIOD)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    value = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}", counter


def _totp(secret: str, now: float) -> str:
    """Return the RFC 6238 code; kept private for deterministic unit tests."""
    return _totp_parts(secret, now)[0]


def _totp_ok(secret: str, code: str, now: float, last_counter: int | None = None) -> tuple[bool, int | None]:
    if not isinstance(code, str) or len(code) != TOTP_DIGITS or not code.isascii() or not code.isdigit():
        return False, None
    try:
        for step in (-1, 0, 1):
            expected, counter = _totp_parts(secret, now + step * TOTP_PERIOD)
            if hmac.compare_digest(expected, code) and (last_counter is None or counter > last_counter):
                return True, counter
    except (ValueError, binascii.Error, struct.error):
        pass
    return False, None


def _recovery_record(code: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16)
    digest = _scrypt(code.encode("ascii"), salt, RECOVERY_N, RECOVERY_R, RECOVERY_P, 32 * 1024 * 1024)
    return base64.b64encode(salt).decode(), base64.b64encode(digest).decode()


def _subject_hash(value: str, secret: bytes) -> str:
    return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()


class AuthenticationService:
    """Durable identity service with no execution or governance authority."""

    def __init__(self, db_path: str | Path, *, master_key: bytes | str | None = None, now: Callable[[], float] = time.time) -> None:
        self.db_path = Path(db_path)
        raw = master_key if master_key is not None else os.environ.get("SINGULAR_AUTH_MASTER_KEY")
        if raw is None:
            raise AuthenticationConfigurationError("SINGULAR_AUTH_MASTER_KEY is required")
        if isinstance(raw, str):
            raw = raw.encode("ascii")
        try:
            self._fernet = Fernet(raw)
        except (ValueError, TypeError):
            raise AuthenticationConfigurationError("invalid authentication master key") from None
        self._rate_secret = hashlib.sha256(raw + b"/rate-limit-v1").digest()
        self._now = now
        self._dummy_salt, self._dummy_digest = _password_record("SINGULAR dummy authentication password")
        self._db = SqliteLocation(self.db_path)
        self._init_db()
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass

    def _connect(self) -> sqlite3.Connection:
        return self._db.connect(foreign_keys=True, busy_timeout=True)

    def _init_db(self) -> None:
        with self._db.session(foreign_keys=True, busy_timeout=True) as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS auth_users(
              user_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
              password_salt TEXT NOT NULL, password_digest TEXT NOT NULL,
              security_version INTEGER NOT NULL DEFAULT 1,
              totp_ciphertext BLOB, pending_totp_ciphertext BLOB, pending_totp_expires REAL,
              last_totp_counter INTEGER, created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS auth_sessions(
              token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
              expires_at REAL NOT NULL, security_version INTEGER NOT NULL, created_at REAL NOT NULL, revoked_at REAL);
            CREATE TABLE IF NOT EXISTS auth_recovery_codes(
              user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
              code_salt TEXT NOT NULL, code_digest TEXT NOT NULL, used_at REAL,
              PRIMARY KEY(user_id, code_digest));
            CREATE TABLE IF NOT EXISTS auth_attempts(
              subject_hash TEXT PRIMARY KEY, failures INTEGER NOT NULL,
              first_failure_at REAL NOT NULL, last_failure_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS auth_audit(event TEXT NOT NULL, user_id TEXT, created_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS auth_sessions_user_idx ON auth_sessions(user_id);
            CREATE INDEX IF NOT EXISTS auth_recovery_user_idx ON auth_recovery_codes(user_id);
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(auth_users)")}
            if "last_totp_counter" not in columns:
                conn.execute("ALTER TABLE auth_users ADD COLUMN last_totp_counter INTEGER")

    @staticmethod
    def _token_hash(token: str) -> str:
        if not isinstance(token, str):
            raise SessionInvalid("invalid session")
        return hashlib.sha256(token.encode("ascii", "strict")).hexdigest()

    def _audit(self, conn: sqlite3.Connection, event: str, user_id: str | None) -> None:
        conn.execute("INSERT INTO auth_audit(event,user_id,created_at) VALUES(?,?,?)", (event, user_id, self._now()))

    def create_user(self, username: str, password: str) -> str:
        username = _login(username)
        salt, digest = _password_record(password)
        user_id = "USR-" + secrets.token_hex(16)
        with self._connect() as conn:
            try:
                conn.execute("INSERT INTO auth_users(user_id,username,password_salt,password_digest,created_at) VALUES(?,?,?,?,?)", (user_id, username, salt, digest, self._now()))
            except sqlite3.IntegrityError:
                raise ValueError("user already exists") from None
            self._audit(conn, "user_created", user_id)
        return user_id

    def begin_totp_enrollment(self, user_id: str, password: str, *, issuer: str = "SINGULAR", otp: str | None = None, recovery_code: str | None = None, now: float | None = None) -> TotpEnrollment:
        current = self._now() if now is None else now
        subject = _subject_hash(user_id, self._rate_secret)
        with self._connect() as conn:
            if self._limited(conn, subject, current):
                raise RateLimited("authentication temporarily unavailable")
            row = conn.execute("SELECT username,password_salt,password_digest,totp_ciphertext,last_totp_counter FROM auth_users WHERE user_id=?", (user_id,)).fetchone()
            if row is None or not _password_ok(password, row["password_salt"], row["password_digest"]):
                self._fail(conn, subject, current)
                self._audit(conn, "login_failed", user_id if row else None)
                conn.commit()
                raise AuthenticationError("authentication failed")
            if row["totp_ciphertext"] is not None:
                if not otp and not recovery_code:
                    raise SecondFactorRequired("second factor required")
                if otp:
                    try:
                        secret = self._fernet.decrypt(row["totp_ciphertext"]).decode("ascii")
                    except (InvalidToken, UnicodeDecodeError):
                        raise AuthenticationConfigurationError("stored authentication secret is invalid") from None
                    ok, counter = _totp_ok(secret, otp, current, row["last_totp_counter"])
                    if not ok:
                        self._fail(conn, subject, current)
                        self._audit(conn, "login_failed", user_id)
                        conn.commit()
                        raise AuthenticationError("authentication failed")
                    cursor = conn.execute("UPDATE auth_users SET last_totp_counter=? WHERE user_id=? AND (last_totp_counter IS NULL OR last_totp_counter < ?)", (counter, user_id, counter))
                    if cursor.rowcount != 1:
                        self._fail(conn, subject, current)
                        self._audit(conn, "login_failed", user_id)
                        conn.commit()
                        raise AuthenticationError("authentication failed")
                elif not self._consume_recovery(conn, user_id, recovery_code or "", current):
                    self._fail(conn, subject, current)
                    self._audit(conn, "login_failed", user_id)
                    conn.commit()
                    raise AuthenticationError("authentication failed")
            self._clear(conn, subject)
            secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
            expires = current + PENDING_TOTP_TTL
            conn.execute("UPDATE auth_users SET pending_totp_ciphertext=?,pending_totp_expires=? WHERE user_id=?", (self._fernet.encrypt(secret.encode()), expires, user_id))
            self._audit(conn, "totp_enrollment_started", user_id)
        label = f"{issuer}:{row['username']}"
        uri = "otpauth://totp/" + quote(label, safe="") + "?" + urlencode({"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": 6, "period": 30})
        return TotpEnrollment(secret, uri, expires)

    def confirm_totp_enrollment(self, user_id: str, code: str, *, now: float | None = None) -> tuple[str, ...]:
        current = self._now() if now is None else now
        subject = _subject_hash(user_id, self._rate_secret)
        with self._connect() as conn:
            if self._limited(conn, subject, current):
                raise RateLimited("authentication temporarily unavailable")
            row = conn.execute("SELECT pending_totp_ciphertext,pending_totp_expires FROM auth_users WHERE user_id=?", (user_id,)).fetchone()
            if row is None or row["pending_totp_ciphertext"] is None or row["pending_totp_expires"] is None or current > row["pending_totp_expires"]:
                self._fail(conn, subject, current)
                self._audit(conn, "login_failed", user_id if row else None)
                conn.commit()
                raise AuthenticationError("authentication failed")
            try:
                secret = self._fernet.decrypt(row["pending_totp_ciphertext"]).decode("ascii")
            except (InvalidToken, UnicodeDecodeError):
                raise AuthenticationConfigurationError("stored authentication secret is invalid") from None
            ok, counter = _totp_ok(secret, code, current)
            if not ok:
                self._fail(conn, subject, current)
                self._audit(conn, "login_failed", user_id)
                conn.commit()
                raise AuthenticationError("authentication failed")
            conn.execute("UPDATE auth_users SET totp_ciphertext=?,pending_totp_ciphertext=NULL,pending_totp_expires=NULL,last_totp_counter=?,security_version=security_version+1 WHERE user_id=?", (self._fernet.encrypt(secret.encode()), counter, user_id))
            conn.execute("DELETE FROM auth_recovery_codes WHERE user_id=?", (user_id,))
            codes: list[str] = []
            for _ in range(10):
                value = secrets.token_hex(8).upper()
                salt, digest = _recovery_record(value)
                conn.execute("INSERT INTO auth_recovery_codes(user_id,code_salt,code_digest) VALUES(?,?,?)", (user_id, salt, digest))
                codes.append(value)
            self._revoke_all(conn, user_id, current)
            self._clear(conn, subject)
            self._audit(conn, "totp_enabled", user_id)
            return tuple(codes)

    def authenticate(self, login: str, password: str, *, otp: str | None = None, recovery_code: str | None = None, client_key: str = "", now: float | None = None) -> str:
        current = self._now() if now is None else now
        normalized = _login(login)
        account = _subject_hash(normalized, self._rate_secret)
        client = _subject_hash(client_key, self._rate_secret) if client_key else None
        with self._connect() as conn:
            if self._limited(conn, account, current) or (client is not None and self._limited(conn, client, current)):
                raise RateLimited("authentication temporarily unavailable")
            row = conn.execute("SELECT * FROM auth_users WHERE username=?", (normalized,)).fetchone()
            password_ok = _password_ok(password, row["password_salt"], row["password_digest"]) if row else _password_ok(password, self._dummy_salt, self._dummy_digest)
            if not password_ok:
                self._fail(conn, account, current)
                if client is not None:
                    self._fail(conn, client, current)
                self._audit(conn, "login_failed", row["user_id"] if row else None)
                conn.commit()
                raise AuthenticationError("authentication failed")
            if row["totp_ciphertext"] is not None:
                if not otp and not recovery_code:
                    raise SecondFactorRequired("second factor required")
                if otp:
                    try:
                        secret = self._fernet.decrypt(row["totp_ciphertext"]).decode("ascii")
                    except (InvalidToken, UnicodeDecodeError):
                        raise AuthenticationConfigurationError("stored authentication secret is invalid") from None
                    ok, counter = _totp_ok(secret, otp, current, row["last_totp_counter"])
                    if not ok:
                        self._fail(conn, account, current)
                        if client is not None:
                            self._fail(conn, client, current)
                        self._audit(conn, "login_failed", row["user_id"])
                        conn.commit()
                        raise AuthenticationError("authentication failed")
                    cursor = conn.execute("UPDATE auth_users SET last_totp_counter=? WHERE user_id=? AND (last_totp_counter IS NULL OR last_totp_counter < ?)", (counter, row["user_id"], counter))
                    if cursor.rowcount != 1:
                        self._fail(conn, account, current)
                        if client is not None:
                            self._fail(conn, client, current)
                        self._audit(conn, "login_failed", row["user_id"])
                        conn.commit()
                        raise AuthenticationError("authentication failed")
                elif not self._consume_recovery(conn, row["user_id"], recovery_code or "", current):
                    self._fail(conn, account, current)
                    if client is not None:
                        self._fail(conn, client, current)
                    self._audit(conn, "login_failed", row["user_id"])
                    conn.commit()
                    raise AuthenticationError("authentication failed")
            self._clear(conn, account)
            if client is not None:
                self._clear(conn, client)
            return self._session(conn, row["user_id"], row["security_version"], current)

    def validate_session(self, token: str, *, now: float | None = None) -> AuthPrincipal:
        current = self._now() if now is None else now
        try:
            token_hash = self._token_hash(token)
        except (UnicodeEncodeError, ValueError):
            raise SessionInvalid("invalid session") from None
        with self._connect() as conn:
            row = conn.execute("SELECT s.*,u.username FROM auth_sessions s JOIN auth_users u ON u.user_id=s.user_id WHERE s.token_hash=?", (token_hash,)).fetchone()
            if row is None or row["revoked_at"] is not None or row["expires_at"] <= current:
                raise SessionInvalid("invalid session")
            user = conn.execute("SELECT security_version FROM auth_users WHERE user_id=?", (row["user_id"],)).fetchone()
            if user is None or user["security_version"] != row["security_version"]:
                raise SessionInvalid("invalid session")
            return AuthPrincipal(row["user_id"], row["username"], row["security_version"])

    def revoke_session(self, token: str) -> None:
        try:
            token_hash = self._token_hash(token)
        except (UnicodeEncodeError, ValueError):
            raise SessionInvalid("invalid session") from None
        with self._connect() as conn:
            conn.execute("UPDATE auth_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL", (self._now(), token_hash))

    def change_password(self, user_id: str, current_password: str, new_password: str) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT password_salt,password_digest FROM auth_users WHERE user_id=?", (user_id,)).fetchone()
            if row is None or not _password_ok(current_password, row["password_salt"], row["password_digest"]):
                raise AuthenticationError("authentication failed")
            salt, digest = _password_record(new_password)
            conn.execute("UPDATE auth_users SET password_salt=?,password_digest=?,security_version=security_version+1 WHERE user_id=?", (salt, digest, user_id))
            self._revoke_all(conn, user_id, self._now())
            self._audit(conn, "password_changed", user_id)

    def disable_totp(self, user_id: str, password: str, *, otp: str | None = None, recovery_code: str | None = None) -> None:
        current = self._now()
        subject = _subject_hash(user_id, self._rate_secret)
        with self._connect() as conn:
            if self._limited(conn, subject, current):
                raise RateLimited("authentication temporarily unavailable")
            row = conn.execute("SELECT password_salt,password_digest,totp_ciphertext,last_totp_counter FROM auth_users WHERE user_id=?", (user_id,)).fetchone()
            if row is None or row["totp_ciphertext"] is None or not _password_ok(password, row["password_salt"], row["password_digest"]):
                self._fail(conn, subject, current)
                self._audit(conn, "login_failed", user_id if row else None)
                conn.commit()
                raise AuthenticationError("authentication failed")
            try:
                secret = self._fernet.decrypt(row["totp_ciphertext"]).decode("ascii")
            except (InvalidToken, UnicodeDecodeError):
                raise AuthenticationConfigurationError("stored authentication secret is invalid") from None
            ok, counter = _totp_ok(secret, otp or "", current, row["last_totp_counter"]) if otp else (self._consume_recovery(conn, user_id, recovery_code or "", current), None)
            if not ok:
                self._fail(conn, subject, current)
                self._audit(conn, "login_failed", user_id)
                conn.commit()
                raise AuthenticationError("authentication failed")
            if otp:
                cursor = conn.execute("UPDATE auth_users SET last_totp_counter=? WHERE user_id=? AND (last_totp_counter IS NULL OR last_totp_counter < ?)", (counter, user_id, counter))
                if cursor.rowcount != 1:
                    self._fail(conn, subject, current)
                    self._audit(conn, "login_failed", user_id)
                    conn.commit()
                    raise AuthenticationError("authentication failed")
            conn.execute("UPDATE auth_users SET totp_ciphertext=NULL,last_totp_counter=?,security_version=security_version+1 WHERE user_id=?", (counter, user_id))
            conn.execute("DELETE FROM auth_recovery_codes WHERE user_id=?", (user_id,))
            self._revoke_all(conn, user_id, current)
            self._clear(conn, subject)
            self._audit(conn, "totp_disabled", user_id)

    def _session(self, conn: sqlite3.Connection, user_id: str, version: int, now: float) -> str:
        token = secrets.token_urlsafe(32)
        conn.execute("INSERT INTO auth_sessions(token_hash,user_id,expires_at,security_version,created_at) VALUES(?,?,?,?,?)", (self._token_hash(token), user_id, now + SESSION_TTL, version, now))
        self._audit(conn, "login_success", user_id)
        return token

    @staticmethod
    def _revoke_all(conn: sqlite3.Connection, user_id: str, now: float) -> None:
        conn.execute("UPDATE auth_sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now, user_id))

    @staticmethod
    def _limited(conn: sqlite3.Connection, subject: str, now: float) -> bool:
        row = conn.execute("SELECT failures,first_failure_at FROM auth_attempts WHERE subject_hash=?", (subject,)).fetchone()
        if row is None:
            return False
        if now - row["first_failure_at"] >= RATE_WINDOW:
            conn.execute("DELETE FROM auth_attempts WHERE subject_hash=?", (subject,))
            return False
        return row["failures"] >= RATE_LIMIT

    @staticmethod
    def _fail(conn: sqlite3.Connection, subject: str, now: float) -> None:
        row = conn.execute("SELECT failures,first_failure_at FROM auth_attempts WHERE subject_hash=?", (subject,)).fetchone()
        if row is None or now - row["first_failure_at"] >= RATE_WINDOW:
            conn.execute("INSERT OR REPLACE INTO auth_attempts VALUES(?,?,?,?)", (subject, 1, now, now))
        else:
            conn.execute("UPDATE auth_attempts SET failures=failures+1,last_failure_at=? WHERE subject_hash=?", (now, subject))

    @staticmethod
    def _clear(conn: sqlite3.Connection, subject: str) -> None:
        conn.execute("DELETE FROM auth_attempts WHERE subject_hash=?", (subject,))

    @staticmethod
    def _consume_recovery(conn: sqlite3.Connection, user_id: str, code: str, now: float) -> bool:
        if not isinstance(code, str) or len(code) != 16 or not code.isascii() or not code.isalnum():
            return False
        rows = conn.execute("SELECT rowid,code_salt,code_digest FROM auth_recovery_codes WHERE user_id=? AND used_at IS NULL", (user_id,)).fetchall()
        for row in rows:
            try:
                actual = _scrypt(code.upper().encode("ascii"), base64.b64decode(row["code_salt"], validate=True), RECOVERY_N, RECOVERY_R, RECOVERY_P, 32 * 1024 * 1024)
                expected = base64.b64decode(row["code_digest"], validate=True)
            except (ValueError, TypeError):
                continue
            if hmac.compare_digest(actual, expected):
                cursor = conn.execute("UPDATE auth_recovery_codes SET used_at=? WHERE rowid=? AND used_at IS NULL", (now, row["rowid"]))
                return cursor.rowcount == 1
        return False


__all__ = ["AuthPrincipal", "AuthenticationConfigurationError", "AuthenticationError", "AuthenticationService", "RateLimited", "SecondFactorRequired", "SessionInvalid", "TotpEnrollment", "generate_master_key"]