"""Offline fault injection. Never loads a SDK, reads credentials, or opens a broker."""
import ast
import importlib.util
import json
import os
import subprocess
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pandas as pd
import pytest

from market_ai_hub.integrations.yuanta import live_quote_recorder as R
from market_ai_hub.research.v2 import calibration_evaluation as CE
from market_ai_hub.research.v2 import prediction_audit as PA


def quote(n=1, **fields):
    return {"market_no": 207, "instrument_code": "TEST", "received_at": f"2026-09-24T00:00:{n:02d}+00:00",
            "timestamp_quality": "LOCAL_RECEIVE_TIME_ONLY", "callback_type": "quote", **fields}


def test_failed_write_retains_batch_and_concurrent_callback(tmp_path, monkeypatch):
    q = R.QuoteBuffer(5)
    q.append(quote(1, DealPrice=100))
    def broken(*args, **kwargs):
        q.append(quote(2, DealPrice=101))
        raise OSError("disk full")
    with monkeypatch.context() as m:
        m.setattr(pd.DataFrame, "to_parquet", broken)
        with pytest.raises(OSError):
            q.flush(tmp_path)
    assert q.snapshot()[1:] == (2, 0)
    assert not list(tmp_path.rglob("*.parquet"))
    assert not list(tmp_path.rglob("*.partial"))
    output = q.flush(tmp_path)
    assert pd.read_parquet(output).DealPrice.tolist() == [100, 101]
    assert q.snapshot()[1] == 0


def test_append_during_successful_write_is_not_acknowledged(tmp_path, monkeypatch):
    q = R.QuoteBuffer(5)
    q.append(quote(1))
    writer = R._write_parquet
    def concurrent(root, records):
        thread = threading.Thread(target=lambda: q.append(quote(2)))
        thread.start()
        thread.join()
        return writer(root, records)
    monkeypatch.setattr(R, "_write_parquet", concurrent)
    q.flush(tmp_path)
    assert q.snapshot()[1] == 1
    assert q.records[0]["received_at"] == quote(2)["received_at"]


def test_bounded_buffer_exposes_loss_and_retains_field_time():
    q = R.QuoteBuffer(1)
    q.append(quote(1, DealPrice=100, source_time_of_day="08:00:00"))
    q.append(quote(2, BuyPrice=99))
    latest, pending, dropped = q.snapshot()
    item = latest["207:TEST"]
    assert (pending, dropped) == (1, 1)
    assert item["field_provenance"]["DealPrice"]["received_at"] == quote(1)["received_at"]
    assert item["field_provenance"]["BuyPrice"]["received_at"] == quote(2)["received_at"]
    assert "source_time_of_day" not in item
    assert item["freshness_semantics"] == "PER_FIELD_ONLY"


def test_quote_buffer_soak_stays_bounded_and_reports_exact_loss():
    q = R.QuoteBuffer(128)
    for n in range(5000):
        q.append({
            "market_no": 207, "instrument_code": "TEST",
            "received_at": f"2026-09-24T00:{n // 60 % 60:02d}:{n % 60:02d}+00:00",
            "timestamp_quality": "LOCAL_RECEIVE_TIME_ONLY", "callback_type": "quote",
            "DealPrice": n,
        })
    latest, pending, dropped = q.snapshot()
    assert pending == 128
    assert dropped == 5000 - 128
    assert latest["207:TEST"]["DealPrice"] == 4999


def test_default_subscription_resolution_is_explicit_asof_not_wall_clock():
    spec = {
        "key": "ose_micro", "market_no": 207, "code_prefix": "JNU",
        "order_root": "JNU", "session_variant": "BOTH", "contracts": 1,
    }
    rows = [
        {"market_code": 207, "code": "JNU2609", "order_code": "JNU 202609"},
        {"market_code": 207, "code": "JNU2612", "order_code": "JNU 202612"},
    ]
    assert R._resolve_spec(spec, rows, asof=date(2026, 9, 1)) == [(207, "JNU2609", "ose_micro")]
    assert R._resolve_spec(spec, rows, asof=date(2026, 9, 24)) == [(207, "JNU2612", "ose_micro")]
    before_jst_rollover = datetime(2026, 9, 10, 14, 30, tzinfo=timezone.utc)
    after_jst_rollover = datetime(2026, 9, 10, 15, 30, tzinfo=timezone.utc)
    assert R._resolve_spec(spec, rows, asof=before_jst_rollover) == [(207, "JNU2609", "ose_micro")]
    assert R._resolve_spec(spec, rows, asof=after_jst_rollover) == [(207, "JNU2612", "ose_micro")]
    with pytest.raises(ValueError, match="timezone-aware"):
        R._resolve_spec(spec, rows, asof=datetime(2026, 9, 10, 15, 30))


def test_subscription_revalidation_is_periodic_not_calendar_day_gate():
    assert not R._subscription_revalidation_due(100.0, 399.9, 300.0)
    assert R._subscription_revalidation_due(100.0, 400.0, 300.0)
    assert R._subscription_revalidation_due(400.0, 700.0, 300.0)


def test_runtime_default_refresh_replaces_contract_and_preserves_dynamic(monkeypatch):
    current_defaults = {(207, "JNU2609"): "ose_micro"}
    subscribed = {(207, "JNU2609"): "ose_micro", (203, "NQZ6"): "dynamic"}
    calls = []
    monkeypatch.setattr(R, "resolve_default_subscriptions",
                        lambda _cfg, *, asof=None: [(207, "JNU2612", "ose_micro")])
    monkeypatch.setattr(R, "_subscribe", lambda _rt, _acct, pairs: calls.append(("add", list(pairs))))
    monkeypatch.setattr(R, "_unsubscribe", lambda _rt, _acct, pairs: calls.append(("remove", list(pairs))))
    out = R._refresh_default_subscriptions(object(), "MASKED", {}, current_defaults, subscribed,
                                           asof=date(2026, 9, 24))
    assert out == {"added": 1, "removed": 1, "desired": 1}
    assert current_defaults == {(207, "JNU2612"): "ose_micro"}
    assert subscribed == {(207, "JNU2612"): "ose_micro", (203, "NQZ6"): "dynamic"}
    assert calls == [
        ("add", [(207, "JNU2612", "ose_micro")]),
        ("remove", [(207, "JNU2609", "ose_micro")]),
    ]


def test_runtime_default_refresh_dynamic_overlap_keeps_dynamic_owner(monkeypatch):
    current_defaults = {(207, "JNU2609"): "ose_micro"}
    subscribed = {(207, "JNU2609"): "ose_micro", (207, "JNU2612"): "dynamic"}
    calls = []
    monkeypatch.setattr(R, "resolve_default_subscriptions",
                        lambda _cfg, *, asof=None: [(207, "JNU2612", "ose_micro")])
    monkeypatch.setattr(R, "_subscribe", lambda _rt, _acct, pairs: calls.append(("add", list(pairs))))
    monkeypatch.setattr(R, "_unsubscribe", lambda _rt, _acct, pairs: calls.append(("remove", list(pairs))))
    dynamic_subscribed = {(207, "JNU2612")}
    out = R._refresh_default_subscriptions(object(), "MASKED", {}, current_defaults, subscribed,
                                           dynamic_subscribed, asof=date(2026, 9, 24))
    assert out == {"added": 1, "removed": 1, "desired": 1}
    assert current_defaults == {(207, "JNU2612"): "ose_micro"}
    assert subscribed == {(207, "JNU2612"): "ose_micro"}
    assert dynamic_subscribed == {(207, "JNU2612")}
    assert calls == [("remove", [(207, "JNU2609", "ose_micro")])]


def test_runtime_default_removal_does_not_unsubscribe_dynamic_overlap(monkeypatch):
    current_defaults = {(207, "JNU2612"): "ose_micro"}
    subscribed = {(207, "JNU2612"): "dynamic"}
    calls = []
    monkeypatch.setattr(R, "resolve_default_subscriptions", lambda _cfg, *, asof=None: [])
    monkeypatch.setattr(R, "_unsubscribe", lambda _rt, _acct, pairs: calls.append(list(pairs)))
    dynamic_subscribed = {(207, "JNU2612")}
    out = R._refresh_default_subscriptions(object(), "MASKED", {}, current_defaults, subscribed,
                                           dynamic_subscribed, asof=date(2026, 9, 24))
    assert out == {"added": 0, "removed": 1, "desired": 0}
    assert current_defaults == {}
    assert subscribed == {(207, "JNU2612"): "dynamic"}
    assert dynamic_subscribed == {(207, "JNU2612")}
    assert calls == []


def test_runtime_default_key_change_does_not_resubscribe(monkeypatch):
    current_defaults = {(207, "JNU2612"): "old_key"}
    subscribed = {(207, "JNU2612"): "old_key"}
    monkeypatch.setattr(R, "resolve_default_subscriptions",
                        lambda _cfg, *, asof=None: [(207, "JNU2612", "new_key")])
    monkeypatch.setattr(R, "_subscribe", lambda *_args, **_kwargs: pytest.fail("unexpected subscribe"))
    monkeypatch.setattr(R, "_unsubscribe", lambda *_args, **_kwargs: pytest.fail("unexpected unsubscribe"))
    out = R._refresh_default_subscriptions(object(), "MASKED", {}, current_defaults, subscribed,
                                           asof=date(2026, 9, 24))
    assert out == {"added": 0, "removed": 0, "desired": 1}
    assert current_defaults == {(207, "JNU2612"): "new_key"}
    assert subscribed == {(207, "JNU2612"): "new_key"}


def test_runtime_default_partial_add_failure_keeps_completed_add_truth(monkeypatch):
    current_defaults = {}
    subscribed = {}
    monkeypatch.setattr(R, "resolve_default_subscriptions", lambda _cfg, *, asof=None: [
        (207, "JNU2612", "ose_micro"), (207, "JNU2703", "ose_micro"),
    ])
    calls = []
    def subscribe(_rt, _acct, pairs):
        calls.append(list(pairs))
        if pairs[0][1] == "JNU2703":
            raise OSError("provider subscribe failed")
    monkeypatch.setattr(R, "_subscribe", subscribe)
    with pytest.raises(OSError):
        R._refresh_default_subscriptions(object(), "MASKED", {}, current_defaults, subscribed,
                                         asof=date(2026, 9, 24))
    assert current_defaults == {(207, "JNU2612"): "ose_micro"}
    assert subscribed == {(207, "JNU2612"): "ose_micro"}
    assert calls == [[(207, "JNU2612", "ose_micro")], [(207, "JNU2703", "ose_micro")]]



def test_runtime_default_refresh_fails_closed_before_transient_total_cap(monkeypatch):
    current_defaults = {(207, "OLD"): "ose_micro"}
    subscribed = {(207, "OLD"): "ose_micro"}
    subscribed.update({(203, f"DYN{n}"): "dynamic" for n in range(1999)})
    monkeypatch.setattr(R, "resolve_default_subscriptions",
                        lambda _cfg, *, asof=None: [(207, "NEW", "ose_micro")])
    monkeypatch.setattr(R, "_subscribe", lambda *_args, **_kwargs: pytest.fail("unexpected subscribe"))
    monkeypatch.setattr(R, "_unsubscribe", lambda *_args, **_kwargs: pytest.fail("unexpected unsubscribe"))
    with pytest.raises(ValueError, match="safe refresh"):
        R._refresh_default_subscriptions(object(), "MASKED", {}, current_defaults, subscribed,
                                         asof=date(2026, 9, 24))
    assert current_defaults == {(207, "OLD"): "ose_micro"}
    assert (207, "NEW") not in subscribed
    assert len(subscribed) == 2000

def test_runtime_default_refresh_failure_preserves_truthful_union(monkeypatch):
    current_defaults = {(207, "JNU2609"): "ose_micro"}
    subscribed = {(207, "JNU2609"): "ose_micro", (203, "NQZ6"): "dynamic"}
    monkeypatch.setattr(R, "resolve_default_subscriptions",
                        lambda _cfg, *, asof=None: [(207, "JNU2612", "ose_micro")])
    monkeypatch.setattr(R, "_subscribe", lambda *_args, **_kwargs: None)
    def fail_remove(*_args, **_kwargs):
        raise OSError("provider unsubscribe failed")
    monkeypatch.setattr(R, "_unsubscribe", fail_remove)
    with pytest.raises(OSError):
        R._refresh_default_subscriptions(object(), "MASKED", {}, current_defaults, subscribed,
                                         asof=date(2026, 9, 24))
    assert current_defaults == {
        (207, "JNU2609"): "ose_micro", (207, "JNU2612"): "ose_micro",
    }
    assert subscribed == {
        (207, "JNU2609"): "ose_micro", (207, "JNU2612"): "ose_micro",
        (203, "NQZ6"): "dynamic",
    }


def test_dynamic_request_on_existing_default_preserves_future_dynamic_intent(tmp_path, monkeypatch):
    cfg = {"recording": {"max_dynamic_subscriptions": 2},
           "dynamic_requests": {"enabled": True, "allowed_markets": [207]}}
    inbox = tmp_path / "control/inbox"
    inbox.mkdir(parents=True)
    (inbox / "keep.json").write_text(json.dumps({
        "action": "subscribe", "market_no": 207, "symbol": "JNU2612",
    }), encoding="utf-8")
    subscribed = {(207, "JNU2612"): "ose_micro"}
    dynamic_subscribed = set()
    monkeypatch.setattr(R, "_subscribe", lambda *_args, **_kwargs: pytest.fail("unexpected subscribe"))
    R._dynamic_requests(tmp_path, cfg, object(), "MASKED", subscribed, dynamic_subscribed)
    assert subscribed == {(207, "JNU2612"): "ose_micro"}
    assert dynamic_subscribed == {(207, "JNU2612")}
    result = json.loads((tmp_path / "control/processed/keep.result.json").read_text(encoding="utf-8"))
    assert result["status"] == "ALREADY_SUBSCRIBED_NOT_LIVE_VERIFIED"


def test_watchlist_all_call_signature_keeps_explicit_optional_language_arg():
    root = Path(__file__).resolve().parents[1]
    vendor = root / "vendor/yuanta_spark/2.2026.0918.0/YuantaSparkAPI_win-x64_Python/YSendOrder.py"
    recorder = root / "src/market_ai_hub/integrations/yuanta/live_quote_recorder.py"

    def counts(path):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        out = {"SubscribeWatchlistAll": [], "UnSubscribeWatchlistAll": []}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in out:
                out[node.func.attr].append(len(node.args))
        return out

    recorder_counts = counts(recorder)
    # Installed 2.2026.0918.0 DLL reflection shows a third optional Lng parameter
    # (default NORMAL); recorder keeps explicit UTF8 rather than changing runtime behavior.
    assert recorder_counts["SubscribeWatchlistAll"] == [3]
    assert recorder_counts["UnSubscribeWatchlistAll"] == [3]
    text = recorder.read_text(encoding="utf-8")
    assert "enumLangType.UTF8" in text

    # The bundled SDK is intentionally not tracked/published. When it exists locally, retain
    # the cross-check that its Python sample legally omits the optional third argument.
    if vendor.exists():
        vendor_counts = counts(vendor)
        assert 2 in vendor_counts["SubscribeWatchlistAll"]
        assert 2 in vendor_counts["UnSubscribeWatchlistAll"]


def test_control_rejects_action_limit_and_traversal(tmp_path, monkeypatch):
    cfg = {"recording": {"max_dynamic_subscriptions": 1},
           "dynamic_requests": {"enabled": True, "allowed_markets": [207]}}
    inbox = tmp_path / "control/inbox"
    inbox.mkdir(parents=True)
    calls = []
    monkeypatch.setattr(R, "_subscribe", lambda *args: calls.append(args))
    requests = [{"action": "order", "market_no": 207, "symbol": "TEST"},
                {"action": "subscribe", "market_no": 207, "symbol": "NEW"}]
    for n, request in enumerate(requests):
        (inbox / f"{n}.json").write_text(json.dumps(request), encoding="utf-8")
    R._dynamic_requests(tmp_path, cfg, None, "fake", {(207, "OLD"): "dynamic"})
    assert not calls
    assert len(list((tmp_path / "control/failed").glob("*.result.json"))) == 2
    cfg["dynamic_requests"]["inbox"] = "../escape"
    with pytest.raises(ValueError):
        R._dynamic_requests(tmp_path, cfg, None, "fake", {})


def test_single_instance_lock_releases_after_error(tmp_path):
    if R.spark_owner_present():
        pytest.skip(
            "a live SPARK quote owner holds the process-global mutex; "
            "this test needs exclusive ownership"
        )
    with pytest.raises(ValueError):
        with R._single_instance(tmp_path):
            with pytest.raises((RuntimeError, OSError)):
                with R._single_instance(tmp_path):
                    pytest.fail("second owner acquired lock")
            raise ValueError("simulated failure")
    with R._single_instance(tmp_path):
        pass


@pytest.mark.parametrize("value", [2.0, -1.0, float("nan"), float("inf"), .7])
def test_audit_tags_cannot_authorize_public_probability(value):
    artifact = PA.ForecastArtifactRecord(artifact_type="CLASS_SCORE", class_label="UP", value=value,
        calibration_status_at_origin="CALIBRATED", calibration_evidence_id="not-real")
    assert not PA.is_public_probability(artifact)


def test_readiness_does_not_migrate_existing_db(tmp_path, monkeypatch):
    path = tmp_path / "old.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute("CREATE TABLE unrelated (x INTEGER)")
    before = path.read_bytes()
    monkeypatch.setattr(CE, "default_audit_db_path", lambda: path)
    result = CE.actual_evaluation_readiness()
    assert result["ACTUAL_PROBABILITY_EVALUATION"] == "BLOCKED"
    assert path.read_bytes() == before
    with duckdb.connect(str(path), read_only=True) as con:
        assert con.execute("SHOW TABLES").fetchall() == [("unrelated",)]


def test_relative_data_root_does_not_depend_on_cwd(tmp_path, monkeypatch):
    from market_ai_hub.config import runtime_paths as paths
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", "relative-data")
    monkeypatch.chdir(tmp_path)
    assert paths.data_root() == paths.project_root() / "relative-data"


def test_yuanta_maintenance_scripts_have_no_machine_specific_project_or_user_paths(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    check_text = (root / "scripts/check_yuanta_futures_com.ps1").read_text(encoding="utf-8")
    setup_text = (root / "scripts/setup_yuanta_futures_x86.ps1").read_text(encoding="utf-8")
    for text in (check_text, setup_text):
        assert r"D:\MARKET_AI_HUB" not in text
        assert r"C:\Users\fishk" not in text
    assert '$env:PYTHONPATH = Join-Path $Root "src"' in check_text
    assert "MARKET_AI_PYTHON_X86" in setup_text
    assert "py -3.11-32" in setup_text
    assert "create sidecar venv failed" in setup_text
    assert "install minimal deps failed" in setup_text

    sdk_roots = [tmp_path / "SDK 一", tmp_path / "SDK 二"]
    monkeypatch.setenv("MARKET_AI_YUANTA_SDK_ROOTS", os.pathsep.join(str(p) for p in sdk_roots))
    module_path = root / "scripts/yuanta_sdk_forensics.py"
    spec = importlib.util.spec_from_file_location("yuanta_sdk_forensics_portability_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.ROOTS == [str(p) for p in sdk_roots]
    assert "fishk" not in module_path.read_text(encoding="utf-8")


def test_build_identity_tracks_new_runtime_configs(tmp_path, monkeypatch):
    from market_ai_hub.services import build_info as build
    monkeypatch.setattr(build, "SOURCE_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    config = tmp_path / "config/yuanta_live_recorder.yaml"
    config.write_text("enabled: true", encoding="utf-8")
    before = build._compute_build_id()
    config.write_text("enabled: false", encoding="utf-8")
    assert build._compute_build_id() != before
    config.write_bytes(b"enabled: true\n")
    lf = build._compute_build_id()
    config.write_bytes(b"enabled: true\r\n")
    assert build._compute_build_id() == lf


@pytest.mark.skipif(os.name != "nt", reason="PowerShell installer")
def test_yuanta_x86_setup_parses_and_invalid_override_fails_before_install():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts/setup_yuanta_futures_x86.ps1"
    missing = root / "definitely-missing-x86-python.exe"
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
         "-PythonX86", str(missing)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "configured 32-bit Python not found" in combined
    assert "ParserError" not in combined
    assert "install minimal deps" not in combined


def test_windows_setup_selects_supported_64bit_python_and_supports_no_download_bootstrap():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts/setup_windows.ps1").read_text(encoding="utf-8-sig")
    assert "struct.calcsize('P')*8" in text
    assert "$info.bits -ne 64" in text
    assert "$info.minor -notin @(11, 12)" in text
    assert "foreach ($preferredMinor in @(12, 11))" in text
    assert "Automatic installation is intentionally disabled" in text
    assert "[switch]$BootstrapOnly" in text
    assert "BOOTSTRAP_ONLY_PASS (no dependency install performed)" in text
    assert "& $pythonPath -m venv .venv" in text
    assert "platform.machine" not in text

    relocation = (root / "scripts/verify_source_relocation_bootstrap.ps1").read_text(encoding="utf-8-sig")
    assert "git -C $Root ls-files" in relocation
    assert "-BootstrapOnly" in relocation
    assert "old_repo_in_syspath" in relocation
    assert "SOURCE_RELOCATION_BOOTSTRAP_PASS" in relocation


@pytest.mark.skipif(os.name != "nt", reason="PowerShell installer")
def test_windows_setup_rejects_fake_32bit_python_before_bootstrap(tmp_path):
    root = Path(__file__).resolve().parents[1]
    fake = tmp_path / "fake-python.cmd"
    fake.write_text(
        '@echo off\n'
        '@echo {"executable":"C:\\\\fake\\\\python.exe","version":"3.12.0","major":3,"minor":12,"bits":32}\n',
        encoding="ascii",
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(root / "scripts/setup_windows.ps1"), "-BootstrapOnly", "-PythonExe", str(fake)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "must be CPython 3.11/3.12 64-bit" in combined
    assert "建立 .venv" not in combined


@pytest.mark.skipif(os.name != "nt", reason="PowerShell installer")
def test_installer_native_failure_is_fatal():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts/setup_windows.ps1").read_text(encoding="utf-8-sig")
    function = text[text.index("function Assert-NativeSuccess"):text.index("function Get-PythonInfo")]
    result = subprocess.run(["powershell", "-NoProfile", "-Command",
        function + '\n$LASTEXITCODE = 17; Assert-NativeSuccess "mock"; exit 0'], capture_output=True)
    assert result.returncode != 0


# ── C1: connected-but-silent feed must be escalated only on a verified-open venue ──
def test_feed_stalled_requires_verified_open_session():
    kw = dict(reconnect_enabled=True, silence_seconds=200, stale_seconds=180,
              since_last_recovery=9999, cooldown_seconds=300)
    assert R._feed_stalled(session_open=True, **kw)                     # open + silent -> escalate
    assert not R._feed_stalled(session_open=False, **kw)                # closed -> normal quiet
    assert not R._feed_stalled(session_open=True, **{**kw, "silence_seconds": 10})
    assert not R._feed_stalled(session_open=True, **{**kw, "since_last_recovery": 1})
    assert not R._feed_stalled(session_open=True, **{**kw, "reconnect_enabled": False})


def test_subscribed_market_open_uses_session_truth():
    ts = datetime(2026, 10, 1, 14, 28, 56, tzinfo=timezone.utc)   # 22:28 Taipei / 23:28 JST
    assert R._subscribed_market_open({3}, ts) is True             # TAIFEX after-hours
    assert R._subscribed_market_open({207}, ts) is True           # OSE night
    assert R._subscribed_market_open({9999}, ts) is False         # unmapped -> never assumed open
    assert R._subscribed_market_open(set(), ts) is False


def test_recorder_wires_stall_recovery_into_the_main_loop():
    src = (Path(__file__).resolve().parents[1] / "src" / "market_ai_hub" / "integrations"
           / "yuanta" / "live_quote_recorder.py").read_text(encoding="utf-8")
    assert "_feed_stalled(" in src
    assert 'connection["faulted"] or stalled_feed' in src
    assert "stall_recoveries" in src
    assert "session_open" in src


def test_spark_owner_present_is_boolean_and_matches_mutex():
    v = R.spark_owner_present()
    assert isinstance(v, bool)
    if os.name != "nt":
        assert v is False
        return
    if v:
        # the helper must agree with the mutex the recorder itself uses
        with pytest.raises(RuntimeError):
            with R._single_instance(Path(__file__).resolve().parent):
                pass


def test_scalar_drops_nonfinite_and_vendor_sentinel_values():
    assert R._scalar(66500.0) == 66500.0
    assert R._scalar(1000) == 1000
    assert R._scalar(True) is True
    assert R._scalar(0.0) == 0.0
    for bad in (float("nan"), float("inf"), float("-inf"), 6.755378e+38, -6.82e38):
        assert R._scalar(bad) is None
    assert R._scalar(None) is None
    assert R._scalar("abc") == "abc"


def test_stall_recovery_is_capped_so_a_venue_outage_cannot_thrash_logins():
    """A restart cannot repair a venue-side outage: past the budget, stop escalating."""
    kw = dict(reconnect_enabled=True, session_open=True, silence_seconds=200, stale_seconds=180,
              since_last_recovery=9999, cooldown_seconds=300)
    assert R._feed_stalled(recoveries=0, max_recoveries=3, **kw)
    assert R._feed_stalled(recoveries=2, max_recoveries=3, **kw)
    assert not R._feed_stalled(recoveries=3, max_recoveries=3, **kw)
    assert not R._feed_stalled(recoveries=100, max_recoveries=3, **kw)
    # the cap must not disable the ordinary cases
    assert not R._feed_stalled(recoveries=0, max_recoveries=3, **{**kw, "session_open": False})
    assert not R._feed_stalled(recoveries=0, max_recoveries=3,
                               **{**kw, "since_last_recovery": 1})


def test_stall_recovery_budget_is_visible_and_resettable():
    src = (Path(__file__).resolve().parents[1] / "src" / "market_ai_hub" / "integrations"
           / "yuanta" / "live_quote_recorder.py").read_text(encoding="utf-8")
    assert "stall_recovery_state" in src
    assert "max_stall_recoveries" in src
    assert "stall_recovery_exhausted" in src
    # the budget resets once callbacks flow again, so a later outage gets a fresh budget
    assert "stall_recoveries = 0" in src


def test_stall_budget_only_resets_after_sustained_health():
    """A flapping feed must not refill the stall budget and defeat the cap."""
    kw = dict(stale_seconds=600, healthy_reset_seconds=900)
    # momentary burst shortly after a recovery -> budget stays spent
    assert not R._stall_budget_reset(callback_silence=5, since_last_recovery=5, **kw)
    # still silent -> no reset
    assert not R._stall_budget_reset(callback_silence=700, since_last_recovery=99999, **kw)
    # sustained health -> budget refilled
    assert R._stall_budget_reset(callback_silence=5, since_last_recovery=1000, **kw)
    # no recovery has ever happened -> reset immediately
    assert R._stall_budget_reset(callback_silence=5, since_last_recovery=10 ** 9, **kw)


def test_thin_session_silence_threshold_is_tolerant():
    """A thin weekend session can be quiet for minutes; the default must exceed 5 minutes."""
    from decimal import Decimal

    src = (Path(__file__).resolve().parents[1] / "src" / "market_ai_hub" / "integrations"
           / "yuanta" / "live_quote_recorder.py").read_text(encoding="utf-8")
    marker = "_DEFAULT_STALE_RECOVERY_SECONDS = "
    value = Decimal(src.split(marker, 1)[1].split("\n", 1)[0].strip())
    assert value >= 300, value
    assert "_DEFAULT_STALE_HEALTHY_RESET_SECONDS = " in src
    assert "stale_recovery_seconds" in src          # surfaced in status for the operator
