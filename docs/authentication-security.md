# SINGULAR authentication security boundary

The future application uses `singular.authentication.AuthenticationService` as a framework-neutral identity boundary. Authentication does **not** authorize missions, tools, capabilities, or effects.

## Credential storage

- Passwords: salted `scrypt` hashes; plaintext passwords never persist.
- TOTP: RFC 6238, 6 digits, 30-second period, ±1 time-step tolerance.
- TOTP secrets: encrypted at rest with Fernet using `SINGULAR_AUTH_MASTER_KEY` supplied outside the repository.
- Recovery codes: 10 one-time 64-bit random codes; only salted `scrypt` hashes persist.
- Sessions: 256-bit random opaque bearer tokens; only SHA-256 token hashes persist.

## Session invalidation

Password changes and TOTP enable/disable increment `security_version` and revoke existing sessions. Sessions also expire after 12 hours and can be explicitly revoked.

TOTP codes are bound to a durable last-used time-step so the same code cannot be replayed successfully.

## Abuse resistance

Failed password/second-factor attempts are durably rate-limited. Optional `client_key` values are HMAC-derived before storage; raw IP/device identifiers are never stored by this module.

## Application requirements

The web/API layer must add:

1. HTTPS only.
2. Browser sessions in `HttpOnly`, `Secure`, `SameSite=Lax` or stricter cookies.
3. CSRF protection for state-changing cookie-authenticated requests.
4. No credentials, session tokens, TOTP secrets, recovery codes, or master keys in logs, telemetry, URLs, analytics, crash reports, or audit payloads.
5. Login errors that do not reveal whether an account exists.
6. Explicit re-authentication for sensitive account/security changes.
7. Authorization through SINGULAR Governor after authentication; identity alone never creates an execution capability.
8. Production secret storage outside Git and outside the application database for `SINGULAR_AUTH_MASTER_KEY`.
9. No automatic account creation from an unauthenticated request.
10. WebAuthn/passkeys may be added later as a separate factor; do not replace this boundary with an ad-hoc implementation.

## Operational rule

If the authentication master key is absent or malformed, startup fails closed. Never generate a production key automatically at runtime.
