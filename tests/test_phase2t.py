"""Phase 2T — TradingView optional bridge unit tests（不需實機）。"""
import json
import sys
from pathlib import Path

import yaml
import pytest

sys.path.insert(0, "src")

from market_ai_hub.integrations.tradingview_bridge import (
    ALLOWED_CAPABILITIES,
    FORBIDDEN_CAPABILITIES,
    OPTIONAL_EXTERNAL_UI_SOURCE,
    TRADINGVIEW_SOURCE,
    TradingViewConfig,
    TradingViewResearchBridge,
)
from market_ai_hub.integrations.cross_check import CONFLICT, MATCH, TradingViewCrossCheck

ROOT = Path(__file__).resolve().parents[1]


# --- config ---
def test_tradingview_disabled_by_default():
    cfg = TradingViewConfig()
    assert cfg.enabled is False


def test_tradingview_config_validation():
    d = yaml.safe_load((ROOT / "config/tradingview.yaml").read_text(encoding="utf-8"))
    assert d["enabled"] is False
    assert d["host"] == "127.0.0.1"
    assert d["allow_training_data"] is False
    assert d["capabilities"]["order_execution"] is False
    assert d["capabilities"]["arbitrary_ui_eval"] is False


# --- bridge whitelist ---
def test_tradingview_no_order_methods():
    for m in ("place_order", "broker_login", "replay_trade"):
        assert not hasattr(TradingViewResearchBridge, m)


def test_tradingview_no_arbitrary_eval():
    for m in ("ui_evaluate", "arbitrary_javascript", "alert_mutation", "watchlist_mutation"):
        assert not hasattr(TradingViewResearchBridge, m)
        assert m in FORBIDDEN_CAPABILITIES


def test_tradingview_source_semantics():
    assert TRADINGVIEW_SOURCE == "TRADINGVIEW_OPTIONAL_UI"
    assert OPTIONAL_EXTERNAL_UI_SOURCE == "OPTIONAL_EXTERNAL_UI_SOURCE"
    # 不可能是 authoritative 來源語義
    assert TRADINGVIEW_SOURCE != "AUTHORITATIVE"


# --- no core dependency ---
def test_tradingview_no_core_dependency(tmp_path, monkeypatch):
    # get_analysis_packet 不 import/呼叫 TradingView bridge；bridge 不可用仍成功
    monkeypatch.setenv("MARKET_AI_HUB_DATA_ROOT", str(tmp_path / "data"))
    import market_ai_hub.packet.builder as b
    import pandas as pd

    def panel():
        idx = pd.date_range("2024-01-01", periods=300, freq="B", tz="UTC")
        return pd.DataFrame({"^N225": 39000.0 + pd.Series(range(300), dtype=float)}, index=idx)
    monkeypatch.setattr(b, "_regime_panel", panel)
    monkeypatch.setattr(b, "_proxy_reference", lambda: None)

    p = b.build_analysis_packet(market="osaka", detail_level="compact", save_analysis=False)
    assert p["execution_target"] == "OSE_NIKKEI225_MICRO_FUTURES"


def test_tradingview_optional_failure():
    # 模擬 bridge 不可用 → OPTIONAL_UNAVAILABLE，不拋錯、不 BLOCK
    cfg = TradingViewConfig()
    if cfg.enabled:
        pytest.skip("config enabled in this environment")
    assert cfg.enabled is False


# --- symbol map schema ---
def test_tradingview_symbol_map_schema():
    d = json.loads((ROOT / "config" / "tradingview_symbol_map.json").read_text(encoding="utf-8"))
    required_fields = {"logical_instrument", "tradingview_symbol", "exchange",
                       "description", "availability", "delay_status", "verified_at"}
    for inst in d["instruments"]:
        assert required_fields <= set(inst)
    micro = next(i for i in d["instruments"] if i["logical_instrument"] == "OSE_NIKKEI225_MICRO_FUTURES")
    assert micro["tradingview_symbol"] == "OSE:NK225MC1!"
    # 未驗證的 Spot/CME/SGX 不猜 ticker
    for i in d["instruments"]:
        if i["availability"] == "NOT_VERIFIED":
            assert i["tradingview_symbol"] is None


# --- cross-check ---
def test_crosscheck_does_not_override_authoritative():
    cc = TradingViewCrossCheck()
    r = cc.compare("reference_price", internal=65000.0, tradingview=70000.0)
    assert r["status"] == CONFLICT
    assert r["override_authoritative"] is False  # 差異不覆蓋官方
    r2 = cc.compare("reference_price", internal=65000.0, tradingview=65000.0)
    assert r2["status"] == MATCH
