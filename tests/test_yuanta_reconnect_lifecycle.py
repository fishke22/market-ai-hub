"""Offline reconnect lifecycle tests. No SDK login or broker calls."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from market_ai_hub.integrations.yuanta import live_quote_recorder as R
from market_ai_hub.integrations.yuanta.reconnect_lifecycle import (
    ReconnectCleanupError,
    ReconnectLifecycleError,
    ReconnectPolicy,
    recover_quote_runtime,
)


class FakeRuntime:
    def __init__(self, *, connect=True, login_code="0001", close_error=False):
        self.connect = connect
        self.login_code = login_code
        self.close_error = close_error
        self.calls = []
        self.on_quote_callback = None

    def instantiate(self):
        self.calls.append("instantiate")

    def open_prod(self):
        self.calls.append("open")

    def wait_connected(self, timeout=15.0):
        self.calls.append(("wait_connected", timeout))
        return self.connect

    def login(self, account, password):
        self.calls.append(("login", account, password))
        return True

    def wait_login(self, timeout=25.0):
        self.calls.append(("wait_login", timeout))
        return SimpleNamespace(received=True, msg_code=self.login_code)

    def logout(self):
        self.calls.append("logout")

    def close(self):
        self.calls.append("close")
        if self.close_error:
            raise OSError("synthetic close failure")

    def dispose(self):
        self.calls.append("dispose")


def policy(**overrides):
    values = {
        "enabled": True,
        "max_attempts": 3,
        "initial_delay_seconds": 0.001,
        "max_delay_seconds": 0.004,
        "connect_timeout_seconds": 2,
        "login_timeout_seconds": 3,
    }
    values.update(overrides)
    return ReconnectPolicy.from_config(values)


def test_policy_is_enabled_for_quote_only_automation():
    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "config/yuanta_live_recorder.yaml").read_text(encoding="utf-8"))
    assert cfg["auto_reconnect"]["enabled"] is True
    assert cfg["recording"]["secret_backend"] == "WINDOWS_CREDENTIAL_MANAGER_ONLY"
    assert cfg["mode"] == "QUOTE_ONLY_PERSISTENT"


def test_policy_validation_and_bounded_backoff():
    p = policy(max_attempts=4, initial_delay_seconds=1, max_delay_seconds=3)
    assert [p.delay_for_attempt(n) for n in range(1, 5)] == [1, 2, 3, 3]
    with pytest.raises(ValueError, match="max_attempts"):
        ReconnectPolicy.from_config({"max_attempts": 0})
    with pytest.raises(ValueError, match="max_delay_seconds"):
        ReconnectPolicy.from_config({"initial_delay_seconds": 5, "max_delay_seconds": 4})


def test_disabled_policy_does_not_retire_or_create_runtime():
    old = FakeRuntime()
    with pytest.raises(ReconnectLifecycleError, match="disabled"):
        recover_quote_runtime(
            old,
            policy=ReconnectPolicy(enabled=False),
            runtime_factory=lambda: pytest.fail("must not create runtime"),
            account="MASKED",
            password_provider=lambda: "MASKED_SECRET",
            subscriptions=[],
            subscribe_fn=lambda *_args: None,
            quote_callback=lambda *_args: None,
            sleep_fn=lambda _delay: None,
        )
    assert old.calls == []


def test_old_runtime_local_cleanup_failure_blocks_new_runtime():
    old = FakeRuntime(close_error=True)
    created = []
    with pytest.raises(ReconnectCleanupError, match="local shutdown"):
        recover_quote_runtime(
            old,
            policy=policy(),
            runtime_factory=lambda: created.append(True),
            account="MASKED",
            password_provider=lambda: "MASKED_SECRET",
            subscriptions=[],
            subscribe_fn=lambda *_args: None,
            quote_callback=lambda *_args: None,
            sleep_fn=lambda _delay: None,
        )
    assert created == []
    assert old.calls == ["logout", "close", "dispose"]


def test_second_attempt_succeeds_and_restores_complete_subscription_union():
    old = FakeRuntime()
    first = FakeRuntime(connect=False)
    second = FakeRuntime()
    candidates = iter([first, second])
    subscribed = []
    sleeps = []
    password_reads = []
    callback = lambda *_args: None

    runtime, result = recover_quote_runtime(
        old,
        policy=policy(max_attempts=2),
        runtime_factory=lambda: next(candidates),
        account="MASKED",
        password_provider=lambda: password_reads.append(True) or "MASKED_SECRET",
        subscriptions=[(207, "JNU2612", "ose_micro"), (203, "NQ", "dynamic")],
        subscribe_fn=lambda rt, account, rows: subscribed.append((rt, account, list(rows))),
        quote_callback=callback,
        sleep_fn=sleeps.append,
    )

    assert runtime is second
    assert result.attempts == 2
    assert result.login_msg_code == "0001"
    assert result.last_error_type == "ConnectionError"
    assert sleeps == [0.001, 0.002]
    assert len(password_reads) == 1
    assert first.calls[-3:] == ["logout", "close", "dispose"]
    assert second.on_quote_callback is callback
    assert subscribed == [(
        second,
        "MASKED",
        [(207, "JNU2612", "ose_micro"), (203, "NQ", "dynamic")],
    )]


def test_failed_candidate_cleanup_failure_stops_retry():
    old = FakeRuntime()
    first = FakeRuntime(connect=False, close_error=True)
    created = [first]
    with pytest.raises(ReconnectCleanupError, match="candidate"):
        recover_quote_runtime(
            old,
            policy=policy(max_attempts=3),
            runtime_factory=lambda: created.pop(0) if created else pytest.fail("must not retry"),
            account="MASKED",
            password_provider=lambda: "MASKED_SECRET",
            subscriptions=[],
            subscribe_fn=lambda *_args: None,
            quote_callback=lambda *_args: None,
            sleep_fn=lambda _delay: None,
        )


def test_resubscribe_failure_retires_each_candidate_and_exhausts_without_secret_leak():
    old = FakeRuntime()
    candidates = [FakeRuntime(), FakeRuntime()]
    created = iter(candidates)
    secret = "MASKED_SECRET_SHOULD_NOT_LEAK"

    with pytest.raises(ReconnectLifecycleError) as excinfo:
        recover_quote_runtime(
            old,
            policy=policy(max_attempts=2),
            runtime_factory=lambda: next(created),
            account="MASKED_TEST_ACCOUNT",
            password_provider=lambda: secret,
            subscriptions=[(207, "JNU2612", "ose_micro")],
            subscribe_fn=lambda *_args: (_ for _ in ()).throw(OSError("synthetic subscribe failure")),
            quote_callback=lambda *_args: None,
            sleep_fn=lambda _delay: None,
        )

    assert "MASKED_TEST_ACCOUNT" not in str(excinfo.value)
    assert secret not in str(excinfo.value)
    assert "last_error=OSError" in str(excinfo.value)
    assert excinfo.value.attempts == 2
    assert excinfo.value.last_error_type == "OSError"
    for candidate in candidates:
        assert candidate.calls[-3:] == ["logout", "close", "dispose"]


def minimal_config(tmp_path, *, auto_reconnect=True):
    cfg = {
        "enabled": True,
        "recording": {
            "raw_jsonl": False,
            "normalized_parquet": True,
            "max_buffer_records": 10,
            "parquet_flush_seconds": 30,
        },
        "auto_reconnect": {
            "enabled": auto_reconnect,
            "max_attempts": 2,
            "initial_delay_seconds": 0.001,
            "max_delay_seconds": 0.002,
            "connect_timeout_seconds": 1,
            "login_timeout_seconds": 1,
        },
        "storage": {"status_file": "status.json", "latest_file": "latest.json"},
        "dynamic_requests": {"enabled": False},
        "tick_detail_measurements": {"enabled": False},
        "subscriptions": [],
        "daytime_context": [],
    }
    path = tmp_path / "recorder.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def allow_offline_start(monkeypatch, *, defaults=None):
    class Guard:
        def scan(self):
            return {"gate": "PASS", "findings": []}

    monkeypatch.setattr(
        "market_ai_hub.integrations.yuanta.order_api_guard.OrderApiExposureGuard",
        Guard,
    )
    monkeypatch.setattr(
        R, "read_profile_credential",
        lambda _profile: SimpleNamespace(username="MASKED_TEST_ACCOUNT"),
    )
    password_reads = []
    monkeypatch.setattr(
        R, "read_profile_password",
        lambda _profile: password_reads.append(True) or "MASKED_TEST_SECRET",
    )
    monkeypatch.setattr(
        R,
        "resolve_default_subscriptions",
        lambda _cfg, *, asof=None: list(defaults or []),
    )
    return password_reads


def test_tick_detail_maintenance_and_auto_reconnect_are_mutually_exclusive(tmp_path, monkeypatch):
    config = minimal_config(tmp_path)
    monkeypatch.setattr(
        R,
        "read_profile_credential",
        lambda _profile: pytest.fail("must reject before credentials"),
    )
    with pytest.raises(ValueError, match="disabled during tick-detail"):
        R._run_locked(
            config,
            tmp_path,
            enable_tick_detail_measurements=True,
        )


def test_recorder_replaces_faulted_runtime_once_and_keeps_subscription_truth(tmp_path, monkeypatch):
    config = minimal_config(tmp_path)
    password_reads = allow_offline_start(
        monkeypatch,
        defaults=[(207, "JNU2612", "ose_micro")],
    )
    events = []
    subscribe_calls = []

    class Runtime:
        def __init__(self, ident, faulted):
            self.ident = ident
            self.faulted = faulted
            self.on_quote_callback = None

        def instantiate(self): events.append((self.ident, "instantiate"))
        def open_prod(self): events.append((self.ident, "open"))
        def wait_connected(self, timeout=15.0): return True
        def login(self, account, password):
            events.append((self.ident, "login"))
            return True
        def wait_login(self, timeout=25.0):
            return SimpleNamespace(received=True, msg_code="0001")
        def pump(self, _seconds): events.append((self.ident, "pump"))
        def connection_snapshot(self):
            return {
                "state": "DISCONNECTED" if self.faulted else "CONNECTED",
                "system_code": 2 if self.faulted else 1,
                "faulted": self.faulted,
            }
        def logout(self): events.append((self.ident, "logout"))
        def close(self): events.append((self.ident, "close"))
        def dispose(self): events.append((self.ident, "dispose"))

    runtimes = iter([Runtime("old", True), Runtime("new", False)])
    monkeypatch.setattr(R, "SparkRuntime", lambda: next(runtimes))
    monkeypatch.setattr(
        R,
        "_subscribe",
        lambda rt, account, rows: subscribe_calls.append((rt.ident, account, list(rows))),
    )
    monkeypatch.setattr(R, "_dynamic_requests", lambda *_args, **_kwargs: True)

    rc = R._run_locked(config, tmp_path)
    assert rc == 0
    assert len(password_reads) == 2
    assert subscribe_calls == [
        ("old", "MASKED_TEST_ACCOUNT", [(207, "JNU2612", "ose_micro")]),
        ("new", "MASKED_TEST_ACCOUNT", [(207, "JNU2612", "ose_micro")]),
    ]
    assert ("old", "logout") in events
    assert events.index(("old", "dispose")) < events.index(("new", "instantiate"))
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "STOPPED"
    assert status["auto_reconnect_enabled"] is True
    assert status["reconnect_successes"] == 1
    assert status["reconnect_attempts_total"] == 1
    assert status["last_reconnect_at"]
    assert status["last_reconnect_error"] is None
    assert status["last_reconnect_retry_error"] is None
