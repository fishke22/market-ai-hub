"""Phase 2Q-F.6 — public whitelist + analyze legacy tool safety + secret store tests。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]


# ── §4/§5/§6：public whitelist ──

def test_public_whitelist_no_confidence():
    from market_ai_hub.services.public_view import sanitize_forecast_dump

    d = {"model": "chronos-2", "confidence": 0.899, "direction": "up",
         "point_forecast": 66000.0, "expected_return": 0.01,
         "quantiles": {"p10": 64000.0, "p50": 65000.0, "p90": 66000.0},
         "class_probabilities": {"class_1": 0.9}, "model_metadata": {}}
    out = sanitize_forecast_dump(d)
    for bad in ("confidence", "direction", "class_probabilities", "class_probabilities_calibrated"):
        assert bad not in out, bad
    assert out["model_name"] == "chronos-2"
    assert "predictive_quantile_range" in out


def test_public_forecast_whitelist_only():
    from market_ai_hub.services.public_view import sanitize_forecast_dump

    d = {"model": "chronos-2", "point_forecast": 100.0, "secret_internal_field": "x", "model_metadata": {}}
    out = sanitize_forecast_dump(d)
    assert "secret_internal_field" not in out
    assert out["view"] == "public"


def test_public_audit_mode_exposes_raw_with_labels():
    from market_ai_hub.services.public_view import sanitize_forecast_dump

    d = {"model": "xgboost", "class_probabilities": {"class_1": 0.9}, "model_metadata": {}}
    out = sanitize_forecast_dump(d, audit=True)
    assert out["UNCALIBRATED_RAW_SCORE"] is True
    assert out["NOT_PROBABILITY"] is True
    assert out["DO_NOT_USE_AS_VALIDATED_DIRECTION"] is True


# ── §8/§13/§39：analyze legacy tool public-safe ──

def test_analyze_osaka_public_safe():
    from market_ai_hub.services.public_view import sanitize_analysis_output

    raw = {
        "symbol": "^N225",
        "chronos": {"model": "chronos-2", "direction": "up", "confidence": 0.9,
                    "class_probabilities": {"class_1": 0.9}, "model_metadata": {}},
        "ensemble": {"model": "ensemble", "direction": "up",
                     "model_metadata": {"direction_status": "NO_VALIDATED_MODEL_CONSENSUS", "direction_value": None}},
        "analysis_direction": "up", "integrated_market_view": "up", "final_direction": "up",
    }
    out = sanitize_analysis_output(raw, market="osaka")
    assert out["semantic_scope"] == "PROXY_ONLY"
    assert out["not_execution_target"] is True
    assert out["not_micro_direct"] is True
    assert "analysis_direction" not in out
    assert "final_direction" not in out
    assert "class_probabilities" not in out["chronos"]
    assert "confidence" not in out["chronos"]


    assert out["research_decision_support"]["research_stance"] == "INSUFFICIENT_EVIDENCE"
    assert out["research_decision_support"]["evidence_scope"] == "PROXY_ONLY"
    assert out["research_decision_support"]["conditional_action_framework"]["execution_order_authorized"] is False


def test_osaka_public_research_stance_is_separate_from_validated_direction():
    from market_ai_hub.services.public_view import sanitize_analysis_output

    raw = {
        "symbol": "^N225",
        "price_forecast_ensemble": {
            "status": "OK",
            "expected_return": 0.00033,
        },
        "direction_classification_ensemble": {
            "status": "NO_ELIGIBLE_VOTES",
            "raw_direction_research": {
                "raw_argmax": {"xgboost": "up", "lightgbm": "up"},
                "raw_class_scores": {
                    "xgboost": {"class_1": 0.55},
                    "lightgbm": {"class_1": 0.77},
                },
            },
        },
        "ensemble": {
            "model": "ensemble",
            "model_metadata": {
                "direction_status": "NO_VALIDATED_MODEL_CONSENSUS",
                "direction_value": None,
                "eligible_direction_vote_count": 0,
            },
        },
        "confidence_inputs": {"model_disagreement": "MEDIUM"},
    }
    out = sanitize_analysis_output(raw, market="osaka")
    ds = out["research_decision_support"]
    assert out["direction_status"] == "NO_VALIDATED_MODEL_CONSENSUS"
    assert out["direction_value"] is None
    assert ds["validated_direction_available"] is False
    assert ds["research_stance"] == "SLIGHT_BULLISH_LEAN"
    assert ds["research_stance_strength"] == "WEAK_UNVALIDATED"
    assert ds["basis"]["price_ensemble_tilt"] == "NEAR_FLAT"
    assert ds["basis"]["raw_classifier_tilt_research_only"] == "UP"
    assert ds["conditional_action_framework"]["current"] == "WAIT_FOR_FRESH_DIRECT_CONFIRMATION"
    assert (
        ds["conditional_action_framework"]["if_fresh_direct_confirms_research_stance"]
        == "PRIORITIZE_BULLISH_RESEARCH_SCENARIO"
    )
    assert "raw_direction_research" not in out["direction_classification_ensemble"]
    assert "raw_class_scores" not in str(out["direction_classification_ensemble"])


def test_analyze_taiwan_public_safe():
    from market_ai_hub.services.public_view import sanitize_analysis_output

    raw = {"symbol": "3706.TW", "xgb": {"model": "xgboost", "direction": "up", "class_probabilities": {"class_1": 0.98}, "model_metadata": {}}}
    out = sanitize_analysis_output(raw, market="taiwan")
    assert "class_probabilities" not in out["xgb"]
    assert "direction" not in out["xgb"]


# ── §17：macro context not causal ──

def test_macro_context_not_causal():
    from market_ai_hub.packet.builder import build_analysis_packet

    p = build_analysis_packet(market="osaka", detail_level="compact", save_analysis=False)
    dp = p["driver_panel"]
    assert dp["evidence_role"] == "CONTEXT_ONLY"
    assert dp["causal_validation"] == "NOT_ESTABLISHED"
    assert dp["trading_edge"] == "NOT_ESTABLISHED"


# ── §33：secret store ──

def test_secret_store_status_no_value(monkeypatch):
    import market_ai_hub.services.secret_store as ss

    monkeypatch.setattr(ss, "_wincred_get", lambda n: "SUPER_SECRET_VALUE")
    st = ss.secret_status("FRED_API_KEY")
    assert st["configured"] is True
    assert st["source"] == "WINCRED"
    assert "SUPER_SECRET_VALUE" not in str(st)


def test_secret_store_env_fallback(monkeypatch):
    import market_ai_hub.services.secret_store as ss

    monkeypatch.setattr(ss, "_wincred_get", lambda n: None)
    monkeypatch.setenv("FRED_API_KEY", "envvalue")
    assert ss.get_secret("FRED_API_KEY") == "envvalue"
    assert ss.secret_status("FRED_API_KEY")["source"] == "ENV"


def test_secret_store_missing(monkeypatch):
    import market_ai_hub.services.secret_store as ss

    monkeypatch.setattr(ss, "_wincred_get", lambda n: None)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    assert ss.get_secret("FRED_API_KEY") == ""
    assert ss.secret_status("FRED_API_KEY")["configured"] is False
    assert ss.secret_status("FRED_API_KEY")["source"] == "NONE"


def test_secret_store_alias(monkeypatch):
    import market_ai_hub.services.secret_store as ss

    monkeypatch.setattr(ss, "_wincred_get", lambda n: "tok" if n == "FINMIND_API_TOKEN" else None)
    # legacy alias FINMIND_TOKEN 應 resolve 到 canonical
    assert ss.get_secret("FINMIND_TOKEN") == "tok"


def test_secret_store_no_repo_file_creation(monkeypatch):
    import market_ai_hub.services.secret_store as ss

    monkeypatch.setattr(ss, "_wincred_get", lambda n: "x")
    ss.get_secret("FRED_API_KEY")
    # 不得寫出任何檔案（此函式純讀取）
    assert not (ROOT / ".env.secret").exists()


# ── §40：predict tools public-safe ──

def test_predict_tools_use_public_sanitizer():
    import inspect

    import market_ai_hub.mcp.server as s

    for fn in (s.predict_chronos, s.predict_timesfm, s.predict_ensemble):
        src = inspect.getsource(fn)
        assert "sanitize_forecast_dump" in src or "sanitize_ensemble_dump" in src, fn.__name__


def test_analyze_tools_have_view_param():
    import inspect

    import market_ai_hub.mcp.server as s

    assert "view" in inspect.signature(s.analyze_osaka_nikkei).parameters
    assert "view" in inspect.signature(s.analyze_taiwan_stock).parameters
