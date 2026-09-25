"""Yuanta live multi-factor durable-contract regression tests."""
from pathlib import Path

import yaml
import pytest

from market_ai_hub.integrations.yuanta.capabilities import PROVIDER_STATUS
from market_ai_hub.integrations.yuanta.spark_futures_quote_probe import _matches_requested_quote

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "config" / "yuanta_live_factor_matrix.yaml"
GUIDE = ROOT / "docs" / "integrations" / "yuanta" / "YUANTA_LIVE_MULTIFACTOR_GUIDE_ZH_TW.md"
REPORT = ROOT / "research" / "phase3" / "reports" / "YUANTA_MULTIFACTOR_LIVE_QUOTE_MATRIX_2026-09-24.md"


def test_callback_requires_exact_market_and_instrument():
    good = {"market_no": 203, "instrument_code": "NQ_2612"}
    assert _matches_requested_quote(good, 203, "NQ_2612")
    assert not _matches_requested_quote(good, 207, "NQ_2612")
    assert not _matches_requested_quote(good, 203, "MNQ2612")
    assert not _matches_requested_quote(None, 203, "NQ_2612")


def test_measured_provider_statuses_are_live():
    assert PROVIDER_STATUS["legacy_domestic_quote"] == "LIVE_CALLBACK_VERIFIED"
    assert PROVIDER_STATUS["spark_securities_taifex_quote"] == "LIVE_CALLBACK_VERIFIED"
    assert PROVIDER_STATUS["spark_securities_ose_quote"] == "LIVE_CALLBACK_VERIFIED"
    assert PROVIDER_STATUS["spark_securities_cme_quote"] == "LIVE_CALLBACK_VERIFIED"
    assert PROVIDER_STATUS["spark_futures"] == "SPARK_FUTURES_ACCOUNT_ENTITLEMENT_BLOCKED"


def test_matrix_keeps_api_families_and_proxy_semantics():
    data = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))
    assert data["spark"]["login_profile"] == "securities"
    assert data["legacy_quote"]["api_family"] == "FUTURES_QUOTE_API_YUANTAQUOTE_COM"
    assert data["routing_policy"]["primary_cross_market_live_provider"] == "SPARK_SECURITIES_PROFILE"
    assert data["routing_policy"]["domestic_taifex_backup_provider"] == "LEGACY_FUTURES_QUOTE"
    assert data["routing_policy"]["cash_futures_identity_separation"] is True
    assert data["routing_policy"]["direct_vs_proxy"]["OSE_MICRO_NIGHT"] == "DIRECT"
    assert data["routing_policy"]["direct_vs_proxy"]["CME_NQ"] == "DERIVATIVE_PROXY"


def test_matrix_contains_measured_cross_market_callbacks():
    data = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))
    measured = {x["representation"]: x["result"] for x in data["spark"]["measured_live"]}
    for key in ("TAIFEX_TMF_NIGHT", "OSE_MICRO_NIGHT", "CME_NQ", "CME_MNQ",
                "CME_ES", "CBOE_VX_FUTURES", "CME_JPY_FUTURES",
                "CBOT_US5Y_FUTURES", "CBOT_US10Y_FUTURES",
                "CME_GOLD_FUTURES", "CME_WTI_FUTURES", "ICE_DXY_FUTURES"):
        assert measured[key] == "LIVE_CALLBACK_VERIFIED"


def test_persistent_recorder_contract_is_single_login_and_parquet_first():
    cfg = yaml.safe_load((ROOT / "config" / "yuanta_live_recorder.yaml").read_text(encoding="utf-8"))
    rec = cfg["recording"]
    assert cfg["mode"] == "QUOTE_ONLY_PERSISTENT"
    assert rec["keep_connection_until_process_exit"] is True
    assert rec["logout_after_agent_use"] is False
    assert rec["normalized_parquet"] is True
    assert rec["raw_jsonl"] is False
    assert cfg["dynamic_requests"]["enabled"] is True
    assert cfg["tick_detail_measurements"]["enabled"] is False
    assert cfg["tick_detail_measurements"]["max_last_count"] == 20


def test_agent_entry_scripts_exist():
    for name in (
        "start_yuanta_live_recorder.ps1",
        "stop_yuanta_live_recorder.ps1",
        "request_yuanta_quote.ps1",
        "request_yuanta_tick_detail_measurement.ps1",
        "get_yuanta_live_status.ps1",
        "check_yuanta_recorder_owner.ps1",
    ):
        assert (ROOT / "scripts" / name).exists()


def test_guide_documents_persistent_hub_and_no_relogin():
    text = GUIDE.read_text(encoding="utf-8")
    assert "常駐 Hub" in text
    assert "agent 使用完不得 logout" in text
    assert "request_yuanta_quote.ps1" in (ROOT / "docs" / "development" / "AGENT_HANDOFF.md").read_text(encoding="utf-8")


@pytest.mark.broker_diagnostic
def test_default_recorder_subscriptions_use_actual_contract_codes_not_near_aliases():
    from market_ai_hub.integrations.yuanta.live_quote_recorder import (
        CONFIG_PATH, _load_config, resolve_default_subscriptions,
    )
    subs = resolve_default_subscriptions(_load_config(CONFIG_PATH))
    codes = {code for _, code, _ in subs}
    assert "TMF8" not in codes
    assert "TXF8" not in codes
    assert "MXF8" not in codes
    assert any(code.startswith("TMFPM") for code in codes)
    assert any(code.startswith("JNUPM") for code in codes)


def test_rebuild_docs_and_source_manifest_exist():
    setup = ROOT / "docs" / "integrations" / "yuanta" / "YUANTA_FROM_SCRATCH_SETUP_ZH_TW.md"
    codes = ROOT / "docs" / "integrations" / "yuanta" / "YUANTA_PRODUCT_CODE_AND_SESSION_RULES_ZH_TW.md"
    manifest = ROOT / "config" / "yuanta_source_manifest.yaml"
    for p in (setup, codes, manifest):
        assert p.exists(), p
    text = setup.read_text(encoding="utf-8")
    for token in ("YuantaSparkAPI_win-x64_Python.zip", "YuantaQuoteAPI_py.zip",
                  "行情API元件及說明文件.zip", "Windows Credential Manager",
                  "start_yuanta_live_recorder.ps1"):
        assert token in text, token


def test_source_manifest_has_official_downloads_and_product_sources():
    m = yaml.safe_load((ROOT / "config" / "yuanta_source_manifest.yaml").read_text(encoding="utf-8"))
    src = m["official_sources"]
    assert src["spark_python_win_x64"]["url"].startswith("https://ys.yuanta.com.tw/")
    assert "行情API元件及說明文件.zip" in src["futures_quote_component"]["url"]
    assert m["product_code_authority"]["spark"]["source"] == "FunctionList.xlsx"
    assert "M.TFX.TXT" in m["local_sources"]["legacy_taifex_table"]


def test_yuanta_credential_bootstrap_is_interactive_and_no_cli_password():
    src = (ROOT / "scripts" / "setup_yuanta_credentials.py").read_text(encoding="utf-8")
    assert "getpass.getpass" in src
    assert "--password" not in src and "--secret" not in src
    assert "write_credential" in src
    assert "CRED_TARGET_SECURITIES" in src and "CRED_TARGET_LEGACY_LOGIN_ID" in src


def test_tick_detail_request_script_uses_single_regex_escape():
    text = (ROOT / "scripts" / "request_yuanta_tick_detail_measurement.ps1").read_text(encoding="utf-8")
    assert r"[ValidatePattern('^JNU\d{4}$')]" in text
    assert r"[ValidatePattern('^JNU\\d{4}$')]" not in text
    assert text.count("action = \"tick_detail_measurement\"") == 1
    assert text.count("YUANTA_TICK_DETAIL_MEASUREMENT_QUEUED") == 1


def test_maintenance_scripts_keep_measurement_runtime_only_and_shutdown_graceful():
    start = (ROOT / "scripts" / "start_yuanta_live_recorder.ps1").read_text(encoding="utf-8")
    stop = (ROOT / "scripts" / "stop_yuanta_live_recorder.ps1").read_text(encoding="utf-8")
    assert "EnableTickDetailMeasurements" in start
    assert "--enable-tick-detail-measurements" in start
    assert "YUANTA_LIVE_RUNNING" in start
    assert "START_FAILED" in start
    assert "YUANTA_LIVE_START_TIMEOUT_NO_FRESH_STATUS" in start
    assert 'action = "shutdown"' in stop
    assert "Stop-Process" not in stop


def test_owner_preflight_is_read_only_parent_child_aware_and_fail_closed():
    text = (ROOT / "scripts" / "check_yuanta_recorder_owner.ps1").read_text(encoding="utf-8")
    assert "status.pid" in text
    assert "owner_invocation_pids" in text
    assert "independent_matching_pids" in text
    assert "SAFE_DEFAULT_OWNER_HEALTHY" in text
    assert "BLOCKED_DUPLICATE_OWNER_RISK" in text
    assert "BLOCKED_RUNTIME_BUILD_STALE" in text
    assert "runtime_build_id" in text and "disk_build_id" in text
    assert "runtime_measurement_gate" in text
    assert "tracked_measurement_gate" in text
    assert "broker_action_performed = $false" in text
    for forbidden in ("Stop-Process", "Start-Process", "YuantaOrd", "logout(", ".login("):
        assert forbidden not in text
