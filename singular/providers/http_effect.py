"""An external effect that really leaves the process: one HTTP request.

This is the smallest honest implementation of EffectProvider. It exists because
every control upstream of it -- the validated decision, the attestation, the
durable capability, the execution lease, the outcome ledger -- was built to
govern something, and until now there was nothing to govern.

The interesting case is not success. It is the request that times out or whose
connection drops after the server may already have acted: the effect is neither
done nor not done, and no amount of retrying can tell you which. That is the
condition the whole recovery protocol exists for, and this provider reports it
honestly as UNKNOWN rather than guessing.

Idempotency is the remote's job as much as ours. The coordinator's provider key
is sent as a header on every attempt, so a server that honours it can recognise
a repeat and return its first answer instead of acting twice. `reconcile` asks
the server what became of that key rather than acting again.
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any

from ..effects import EffectRequest, EffectStatus, ProviderResult

#: Header carrying the coordinator's provider idempotency key.
IDEMPOTENCY_HEADER = "Idempotency-Key"
#: Header naming the operation, so a server can route without parsing the body.
OPERATION_HEADER = "X-Singular-Operation"


class HttpProviderError(RuntimeError):
    """The provider could not be configured, as opposed to the call failing."""


class HttpEffectProvider:
    """Perform one HTTP request as a governed external effect.

    Deliberately not a general HTTP client: it takes one endpoint, sends one
    JSON body, and reports one of COMPLETED, FAILED or UNKNOWN. A provider that
    could do many different things would make the decision's provider/operation
    binding meaningless.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        method: str = "POST",
        timeout: float = 10.0,
        headers: dict[str, str] | None = None,
        reconcile_endpoint: str | None = None,
    ) -> None:
        if not endpoint.strip():
            raise HttpProviderError("an endpoint is required")
        if not endpoint.startswith(("http://", "https://")):
            raise HttpProviderError("endpoint must be an http or https URL")
        if timeout <= 0:
            raise HttpProviderError("timeout must be positive")
        self.endpoint = endpoint
        self.method = method.upper()
        self.timeout = timeout
        self.headers = dict(headers or {})
        #: Where to ask what became of an idempotency key. Without it, an
        #: ambiguous effect can never be resolved by asking, only by a human.
        self.reconcile_endpoint = reconcile_endpoint

    def execute(self, request: EffectRequest, idempotency_key: str) -> ProviderResult:
        return self._call(self.endpoint, self.method, request.payload, idempotency_key, request.operation)

    def reconcile(self, request: EffectRequest, idempotency_key: str) -> ProviderResult:
        """Ask the remote what became of this key. Never act again.

        Reconciliation exists precisely because the first attempt may have
        succeeded. Repeating it would be the double execution the whole boundary
        is built to prevent.
        """
        if not self.reconcile_endpoint:
            return ProviderResult(
                EffectStatus.UNKNOWN.value,
                error="no reconcile endpoint is configured; this effect can only be resolved by a human",
            )
        return self._call(self.reconcile_endpoint, "GET", None, idempotency_key, request.operation)

    def _call(self, url: str, method: str, payload: Any, idempotency_key: str, operation: str) -> ProviderResult:
        body = None if payload is None else json.dumps(payload, sort_keys=True).encode("utf-8")
        headers = {
            **self.headers,
            IDEMPOTENCY_HEADER: idempotency_key,
            OPERATION_HEADER: operation,
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        http_request = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout) as response:
                return self._completed(response.status, response.read())
        except urllib.error.HTTPError as exc:
            # The server answered. Whatever it said, it said it -- there is no
            # ambiguity about whether the request arrived.
            return ProviderResult(
                EffectStatus.FAILED.value,
                result=self._decode(exc.read()),
                error=f"HTTP {exc.code}",
            )
        except (TimeoutError, socket.timeout) as exc:
            # The request may have been fully processed before the clock ran out.
            return ProviderResult(EffectStatus.UNKNOWN.value, error=f"timeout after {self.timeout}s: {exc}")
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, (TimeoutError, socket.timeout)):
                return ProviderResult(EffectStatus.UNKNOWN.value, error=f"timeout after {self.timeout}s: {reason}")
            if isinstance(reason, ConnectionRefusedError):
                # Refused before anything was read: nothing happened remotely.
                return ProviderResult(EffectStatus.FAILED.value, error=f"connection refused: {reason}")
            # A connection that dropped mid-flight cannot be distinguished from
            # one that was never established, so it stays ambiguous.
            return ProviderResult(EffectStatus.UNKNOWN.value, error=f"transport failure: {reason}")
        except OSError as exc:
            return ProviderResult(EffectStatus.UNKNOWN.value, error=f"transport failure: {exc}")

    @staticmethod
    def _completed(status: int, raw: bytes) -> ProviderResult:
        decoded = HttpEffectProvider._decode(raw)
        if 200 <= status < 300:
            return ProviderResult(EffectStatus.COMPLETED.value, result={"status": status, "body": decoded})
        return ProviderResult(EffectStatus.FAILED.value, result={"status": status, "body": decoded}, error=f"HTTP {status}")

    @staticmethod
    def _decode(raw: bytes) -> Any:
        text = raw.decode("utf-8", errors="replace")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text


__all__ = ["IDEMPOTENCY_HEADER", "OPERATION_HEADER", "HttpEffectProvider", "HttpProviderError"]
