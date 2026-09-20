"""Phase 2Q-F.4 — runtime output contract enforcement + proxy/direct presentation + Taiwan session filter tests。"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]


# ── §9/§12：direction contract ──

def _clf(model, direction, vote_eligible=False):
    from market_ai_hub.schemas.market_data import DataGrade, ForecastOutput

    return ForecastOutput(
        model=model, symbol="X", as_of=datetime.now(timezone.utc), horizon="1d",
        point_forecast=100.0, expected_return=0.0,
        quantiles={"p10": None, "p50": None, "p90": None},
        direction=direction, confidence=0.5, data_grade=DataGrade.RESEARCH_PROXY,
        model_task="DIRECTION_CLASSIFICATION",
        eligible_for_direction_vote=vote_eligible,
        class_probabilities={"class_-1": 0.4, "class_0": 0.3, "class_1": 0.3},
        class_probabilities_calibrated=False,
        probability_calibrated=False,
    )


def test_direction_contract_zero_votes():
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight

    ens = ensemble_equal_weight([_clf("xgboost", "down"), _clf("lightgbm", "down")], "X", "1d")
    mm = ens.model_metadata
    assert mm["direction_status"] == "NO_VALIDATED_MODEL_CONSENSUS"
    assert mm["direction_value"] is None
    assert mm["eligible_direction_vote_count"] == 0
    assert mm["validated_direction_agreement"] == "N/A"


def test_direction_contract_with_votes():
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight

    ens = ensemble_equal_weight([_clf("xgboost", "up", True), _clf("lightgbm", "up", True)], "X", "1d")
    mm = ens.model_metadata
    assert mm["direction_status"] == "VALIDATED_CONSENSUS"
    assert mm["direction_value"] == "up"


def test_raw_agreement_not_consensus():
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight

    ens = ensemble_equal_weight([_clf("xgboost", "down"), _clf("lightgbm", "down")], "X", "1d")
    mm = ens.model_metadata
    # raw agreement 可 HIGH，但 direction_status 仍 NO_VALIDATED_MODEL_CONSENSUS
    assert mm["legacy_raw_unvalidated_agreement"] in ("HIGH", "MEDIUM", "LOW")
    assert mm["direction_status"] == "NO_VALIDATED_MODEL_CONSENSUS"


# ── §22：display policy ──

def test_display_policy_in_packet():
    from market_ai_hub.packet.builder import build_analysis_packet

    p = build_analysis_packet(market="osaka", detail_level="compact", save_analysis=False)
    dp = p["display_policy"]
    assert dp["may_present_direction"] is False
    assert dp["may_present_probabilities"] is False
    assert dp["may_present_support_resistance"] is False
    assert dp["may_present_trading_advice"] is False


# ── §27：Osaka golden payload ──

def test_osaka_golden_payload():
    from market_ai_hub.packet.builder import build_analysis_packet

    p = build_analysis_packet(market="osaka", detail_level="compact", save_analysis=False)
    ts = p["target_semantics"]
    assert ts["direct_target"] == "OSE_NIKKEI225_MICRO_FUTURES"
    assert ts["direct_micro_forecast_status"] == "NOT_AVAILABLE"
    assert ts["proxy_model_target"] == "^N225"
    assert ts["direct_market_calendar"] == "OSE/JPX_DERIVATIVES"
    assert ts["proxy_model_calendar"] == "XTKS"
    assert "direct_next_sessions" in ts  # machine-readable dates


def test_osaka_direct_sessions_include_holiday_trading():
    from market_ai_hub.services.calendar import next_ose_derivatives_sessions

    sessions = next_ose_derivatives_sessions("2026-09-18", 5)
    assert sessions[:3] == ["2026-09-21", "2026-09-22", "2026-09-23"]


# ── §28：2330 golden payload ──

def test_2330_golden_payload(monkeypatch):
    import market_ai_hub.packet.builder as b

    monkeypatch.setattr(b, "_load_latest_micro_settlement", lambda: {"price": 999999, "contract": "202703", "date": "2026-09-18", "price_type": "SETTLEMENT"})
    monkeypatch.setattr(b, "_taiwan_stock_reference", lambda s: {"price": 123.45, "price_type": "REFERENCE", "source": "twse", "data_grade": "OFFICIAL_DAILY"})
    p = b.build_analysis_packet(market="taiwan", target="2330.TW", detail_level="compact", save_analysis=False)
    assert p["execution_target"] == "2330.TW"
    assert p["reference_price"] == 123.45
    assert p["contract_month"] in ("", None)
    assert p["target_semantics"]["direct_target"] == "2330.TW"


# ── §19/§29：Taiwan weekend session filter ──

def test_taiwan_weekend_bar_excluded():
    import pandas as pd

    from market_ai_hub.services.calendar import sanitize_daily_exchange_sessions

    df = pd.DataFrame({
        "timestamp_utc": pd.to_datetime(["2026-09-18T06:00:00Z", "2026-09-20T06:00:00Z"]),
        "timestamp_local": pd.to_datetime(["2026-09-18T14:00:00+08:00", "2026-09-20T14:00:00+08:00"]),
        "close": [47180.75, 47368.04],
    })
    clean = sanitize_daily_exchange_sessions(df, "^TWII")
    assert len(clean) == 1
    assert clean.iloc[0]["close"] == 47180.75  # Friday retained, Sunday dropped


def test_taiex_reference_session_valid():
    from market_ai_hub.packet.builder import _index_proxy_reference
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider

    # 實測（若無網路會 return None；有網路時 reference_session_valid=True）
    ref = _index_proxy_reference()
    if ref is not None:
        assert ref.get("reference_session_valid") is True


# ── §5：predict_ensemble scope ──

def test_predict_ensemble_proxy_scope():
    import market_ai_hub.mcp.server as s

    # 不真正跑 inference；驗證 output 結構含 forecast_scope 欄位（透過 module 靜態檢查）
    import inspect

    src = inspect.getsource(s.predict_ensemble)
    assert "forecast_scope" in src
    assert "do_not_relabel_as_direct" in src
    assert "direct_forecast" in src
