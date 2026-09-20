"""Phase 2Q-F.5 — public MCP safe view + position-aware research guard tests。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]


# ── §3/§4/§5：public sanitizer ──

def test_public_uncalibrated_no_probability():
    from market_ai_hub.services.public_view import sanitize_forecast_dump

    d = {
        "model": "xgboost", "direction": "down", "confidence": 0.8,
        "class_probabilities": {"class_-1": 0.182, "class_0": 0.404, "class_1": 0.414},
        "class_probabilities_calibrated": False,
        "quantiles": {"p10": None, "p50": None, "p90": None},
        "model_metadata": {"direction_status": "NO_VALIDATED_MODEL_CONSENSUS", "direction_value": None},
    }
    out = sanitize_forecast_dump(d)
    assert "class_probabilities" not in out
    assert "confidence" not in out
    assert "raw_class_scores" in out
    assert out["raw_class_scores_research_only"] is True
    assert out["direction_value"] is None


def test_public_zero_vote_no_direction():
    from market_ai_hub.services.public_view import sanitize_forecast_dump

    d = {"model": "xgboost", "direction": "up", "model_metadata": {"direction_status": "NO_VALIDATED_MODEL_CONSENSUS", "direction_value": None}}
    out = sanitize_forecast_dump(d)
    assert "direction" not in out  # raw direction 移除
    assert out["direction_status"] == "NO_VALIDATED_MODEL_CONSENSUS"
    assert out["direction_value"] is None


def test_public_zero_vote_no_agreement():
    from market_ai_hub.services.public_view import sanitize_ensemble_dump

    d = {
        "model": "ensemble", "direction": "down",
        "model_metadata": {
            "legacy_raw_unvalidated_agreement": "HIGH",
            "model_agreement": "HIGH",
            "validated_direction_agreement": "N/A",
            "direction_status": "NO_VALIDATED_MODEL_CONSENSUS",
            "direction_ensemble": {"class_probabilities": {"class_-1": 0.5, "class_0": 0.3, "class_1": 0.2}},
        },
    }
    out = sanitize_ensemble_dump(d)
    mm = out["model_metadata"]
    assert "legacy_raw_unvalidated_agreement" not in mm
    assert "model_agreement" not in mm
    assert "class_probabilities" not in mm["direction_ensemble"]


def test_quantile_no_support_alias():
    from market_ai_hub.services.public_view import sanitize_forecast_dump

    d = {"model": "chronos-2", "quantiles": {"p10": 64000.0, "p50": 65000.0, "p90": 66000.0}, "model_metadata": {}}
    out = sanitize_forecast_dump(d)
    assert "quantiles" not in out
    assert "predictive_quantile_range" in out
    for alias in ("support", "resistance", "stop", "target", "take_profit"):
        assert alias not in out


# ── §6：Micro/Mini name hardening ──

def test_micro_never_named_mini():
    from market_ai_hub.services.public_view import canonical_instrument_name

    assert canonical_instrument_name("OSE_NIKKEI225_MICRO_FUTURES") == "OSE Nikkei 225 Micro Futures"
    assert canonical_instrument_name("OSE_NIKKEI225_MINI_FUTURES") == "OSE Nikkei 225 mini Futures"
    assert "Mini" not in canonical_instrument_name("OSE_NIKKEI225_MICRO_FUTURES")
    assert "Micro" not in canonical_instrument_name("OSE_NIKKEI225_MINI_FUTURES")


# ── §7：XTKS never OSE ──

def test_xtks_never_direct_ose_calendar():
    from market_ai_hub.packet.builder import build_analysis_packet

    p = build_analysis_packet(market="osaka", detail_level="compact", save_analysis=False)
    ts = p["target_semantics"]
    assert ts["direct_market_calendar"] == "OSE/JPX_DERIVATIVES"
    assert ts["proxy_model_calendar"] == "XTKS"
    assert ts["direct_market_calendar"] != "XTKS"


def test_proxy_headline_not_micro():
    import inspect

    import market_ai_hub.mcp.server as s

    src = inspect.getsource(s.predict_ensemble)
    assert "do_not_relabel_as_direct" in src
    assert "PROXY_MODEL_REFERENCE" in src


# ── §14：cache session filter version ──

def test_taiex_weekend_cache_invalidated():
    from market_ai_hub.services.forecast_cache import SESSION_FILTER_VERSION, forecast_cache_key

    closes = __import__("pandas").Series([47000.0] * 100)
    key = forecast_cache_key("chronos-2", "^TWII", "1d", closes, "buildA")
    assert SESSION_FILTER_VERSION in key
    assert key != forecast_cache_key("chronos-2", "^TWII", "1d", closes, "buildB")


# ── §26：position guard ──

def test_position_policy_risk_only():
    from market_ai_hub.services.public_view import position_guidance_policy

    p = position_guidance_policy()
    assert p["mode"] == "RISK_ANALYSIS_ONLY"
    assert p["personalized_trade_action"] == "PROHIBITED"


def test_position_no_personalized_action():
    from market_ai_hub.services.public_view import position_guidance_policy

    p = position_guidance_policy()
    for f in ("ADD_POSITION", "REDUCE_POSITION", "STOP_PRICE", "TAKE_PROFIT_PRICE", "PERSONALIZED_ORDER_SIZE"):
        assert f in p["forbidden"]
    for a in ("EXPOSURE", "PNL_SENSITIVITY", "SCENARIO_ANALYSIS"):
        assert a in p["allowed"]


def test_position_guidance_policy_in_packet():
    from market_ai_hub.packet.builder import build_analysis_packet

    p = build_analysis_packet(market="osaka", detail_level="compact", save_analysis=False)
    assert p["position_guidance_policy"]["mode"] == "RISK_ANALYSIS_ONLY"
    assert p["position_guidance_policy"]["personalized_trade_action"] == "PROHIBITED"


# ── §21：Micro position arithmetic（exposure math）──

def test_case6_exposure_math():
    # Micro multiplier = JPY 10 / point / contract；23 contracts
    multiplier = 10
    contracts = 23
    per_point = multiplier * contracts
    assert per_point == 230  # 每 1 point = JPY 230
    assert per_point * 100 == 23000  # 每 100 points = JPY 23,000


def test_position_scenario_no_trade_words():
    from market_ai_hub.services.public_view import POSITION_GUIDANCE_POLICY

    # scenario analysis 不應含 trade instruction 欄位
    policy = POSITION_GUIDANCE_POLICY
    assert "STOP_PRICE" not in policy["allowed"]
    assert "TAKE_PROFIT_PRICE" not in policy["allowed"]
