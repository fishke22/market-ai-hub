"""Bounded SPARK quote-runtime replacement after a verified connection fault.

This module does not invent a hidden reconnect API.  It follows the documented
lifecycle surface: retire the faulted object, create a fresh runtime, Open,
wait for official Connect, Login and its OnResponse result, then re-subscribe
the recorder's complete desired quote set.  Live use remains config-gated.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable, Iterable


class ReconnectLifecycleError(RuntimeError):
    def __init__(self, message: str, *, attempts: int = 0, last_error_type: str | None = None):
        super().__init__(message)
        self.attempts = int(attempts)
        self.last_error_type = last_error_type


class ReconnectCleanupError(ReconnectLifecycleError):
    pass


@dataclass(frozen=True)
class ReconnectPolicy:
    enabled: bool = False
    max_attempts: int = 3
    initial_delay_seconds: float = 5.0
    max_delay_seconds: float = 30.0
    connect_timeout_seconds: float = 15.0
    login_timeout_seconds: float = 25.0

    @classmethod
    def from_config(cls, value: dict | None) -> "ReconnectPolicy":
        cfg = value or {}
        policy = cls(
            enabled=bool(cfg.get("enabled", False)),
            max_attempts=int(cfg.get("max_attempts", 3)),
            initial_delay_seconds=float(cfg.get("initial_delay_seconds", 5.0)),
            max_delay_seconds=float(cfg.get("max_delay_seconds", 30.0)),
            connect_timeout_seconds=float(cfg.get("connect_timeout_seconds", 15.0)),
            login_timeout_seconds=float(cfg.get("login_timeout_seconds", 25.0)),
        )
        policy.validate()
        return policy

    def validate(self) -> None:
        if self.max_attempts < 1 or self.max_attempts > 10:
            raise ValueError("auto_reconnect.max_attempts must be 1..10")
        for name, value in (
            ("initial_delay_seconds", self.initial_delay_seconds),
            ("max_delay_seconds", self.max_delay_seconds),
            ("connect_timeout_seconds", self.connect_timeout_seconds),
            ("login_timeout_seconds", self.login_timeout_seconds),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"auto_reconnect.{name} must be finite and > 0")
        if self.max_delay_seconds < self.initial_delay_seconds:
            raise ValueError("auto_reconnect.max_delay_seconds must be >= initial_delay_seconds")

    def delay_for_attempt(self, attempt: int) -> float:
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        return min(self.max_delay_seconds, self.initial_delay_seconds * (2 ** (attempt - 1)))


@dataclass(frozen=True)
class ReconnectResult:
    attempts: int
    login_msg_code: str
    last_error_type: str | None = None


def _retire_runtime(runtime, *, allow_logout_failure: bool) -> None:
    if runtime is None:
        return
    try:
        runtime.logout()
    except Exception:
        if not allow_logout_failure:
            raise ReconnectCleanupError("runtime logout failed")
    local_errors = []
    for name in ("close", "dispose"):
        try:
            getattr(runtime, name)()
        except Exception as exc:
            local_errors.append(type(exc).__name__)
    if local_errors:
        raise ReconnectCleanupError("runtime local shutdown failed")


def recover_quote_runtime(
    old_runtime,
    *,
    policy: ReconnectPolicy,
    runtime_factory: Callable[[], object],
    account: str,
    password_provider: Callable[[], str | None],
    subscriptions: Iterable[tuple[int, str, str]],
    subscribe_fn: Callable[[object, str, list[tuple[int, str, str]]], None],
    quote_callback,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[object, ReconnectResult]:
    """Replace a faulted runtime and restore the complete desired quote subscription set."""
    policy.validate()
    if not policy.enabled:
        raise ReconnectLifecycleError("auto reconnect disabled")
    if not str(account or "").strip():
        raise ValueError("account required")
    desired = list(subscriptions)

    # A second runtime is never created until the old local object is closed/disposed.
    # Logout failure is tolerated because the triggering condition is a connection fault;
    # local Close/Dispose failure is not tolerated because duplicate-owner risk is unknown.
    _retire_runtime(old_runtime, allow_logout_failure=True)

    last_error_type: str | None = None
    for attempt in range(1, policy.max_attempts + 1):
        sleep_fn(policy.delay_for_attempt(attempt))
        candidate = runtime_factory()
        try:
            candidate.instantiate()
            candidate.open_prod()
            if not candidate.wait_connected(timeout=policy.connect_timeout_seconds):
                raise ConnectionError("SPARK reconnect did not receive official Connect")
            password = password_provider()
            if not password:
                raise RuntimeError("SPARK reconnect credential unavailable")
            accepted = candidate.login(account, password)
            password = None
            if not accepted:
                raise RuntimeError("SPARK reconnect login request rejected")
            outcome = candidate.wait_login(timeout=policy.login_timeout_seconds)
            if not outcome.received or outcome.msg_code not in ("0001", "00001"):
                raise RuntimeError("SPARK reconnect login result failed")
            candidate.on_quote_callback = quote_callback
            subscribe_fn(candidate, account, desired)
            return candidate, ReconnectResult(
                attempts=attempt,
                login_msg_code=str(outcome.msg_code),
                last_error_type=last_error_type,
            )
        except Exception as exc:
            last_error_type = type(exc).__name__
            try:
                _retire_runtime(candidate, allow_logout_failure=True)
            except ReconnectCleanupError:
                raise ReconnectCleanupError(
                    "failed reconnect candidate could not be retired",
                    attempts=attempt,
                    last_error_type=last_error_type,
                ) from None

    raise ReconnectLifecycleError(
        f"auto reconnect exhausted after {policy.max_attempts} attempts; last_error={last_error_type}",
        attempts=policy.max_attempts,
        last_error_type=last_error_type,
    )
