"""Offline fault injection. Never loads a SDK, reads credentials, or opens a broker."""
import importlib.util
import json
import os
import subprocess
import threading
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
