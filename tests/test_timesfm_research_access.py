from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from market_ai_hub.services.model_governance import (
    ModelUsageBlocked,
    TIMESFM3_PERSONAL_RESEARCH_ACK,
    timesfm3_research_access_gate,
)


def test_timesfm_research_gate_requires_explicit_personal_nonproduction_ack():
    blocked = timesfm3_research_access_gate("")
    assert blocked["allowed"] is False
    assert blocked["reason"] == "PERSONAL_RESEARCH_ACK_REQUIRED"
    assert blocked["commercial_use_allowed"] is False
    assert blocked["production_use_allowed"] is False
    assert blocked["automatic_download_allowed"] is False
    assert blocked["future_covariates_allowed"] is False


def test_timesfm_research_gate_fails_when_exact_snapshot_missing(tmp_path):
    decision = timesfm3_research_access_gate(
        TIMESFM3_PERSONAL_RESEARCH_ACK,
        cache_dir=tmp_path,
    )
    assert decision["allowed"] is False
    assert "PINNED_SNAPSHOT_MISSING" in decision["failures"]


def test_timesfm_research_gate_matches_local_pinned_runtime():
    decision = timesfm3_research_access_gate(TIMESFM3_PERSONAL_RESEARCH_ACK)
    assert decision["allowed"] is True
    assert decision["package_version_expected"] == "3.0.2"
    assert decision["package_version_observed"] == "3.0.2"
    assert decision["revision"] == "43046b85ec22d584a13f8098c2ed39c889e129c2"
    assert decision["weight_license"] == "timesfm-non-commercial-license-v1.0"


def test_timesfm_research_singleton_is_separate_from_serving(monkeypatch):
    import market_ai_hub.services.model_runtime as runtime

    runtime._timesfm_research = None
    runtime._timesfm = None

    class FakeAdapter:
        def __init__(self, *, purpose):
            self.purpose = purpose

    monkeypatch.setattr(
        "market_ai_hub.models.timesfm_model.TimesFM3Adapter",
        FakeAdapter,
    )
    research = runtime.get_timesfm_research(TIMESFM3_PERSONAL_RESEARCH_ACK)
    serving = runtime.get_timesfm()
    assert research.purpose == "RESEARCH"
    assert serving.purpose == "SERVING"
    assert research is not serving


def test_timesfm_research_singleton_revalidates_ack_after_initialization():
    import market_ai_hub.services.model_runtime as runtime

    runtime._timesfm_research = None
    runtime.get_timesfm_research(TIMESFM3_PERSONAL_RESEARCH_ACK)
    with pytest.raises(ModelUsageBlocked, match="PERSONAL_RESEARCH_ACK_REQUIRED"):
        runtime.get_timesfm_research("wrong")


def test_predict_timesfm_blocks_before_market_fetch_without_ack(monkeypatch):
    import market_ai_hub.mcp.server as server

    called = {"fetch": 0}

    def fail_fetch(*args, **kwargs):
        called["fetch"] += 1
        raise AssertionError("market fetch must not happen before research acknowledgement")

    monkeypatch.setattr(
        "market_ai_hub.providers.yfinance_provider.YFinanceProvider.fetch",
        fail_fetch,
    )
    result = server.predict_timesfm("^TWII", research_usage_ack="")
    assert result["status"] == "RESEARCH_ONLY_BLOCKED"
    assert result["reason"] == "PERSONAL_RESEARCH_ACK_REQUIRED"
    assert called["fetch"] == 0


def test_predict_timesfm_ack_uses_research_runtime_not_serving(monkeypatch):
    import market_ai_hub.mcp.server as server

    ts = pd.date_range("2026-01-01", periods=140, freq="B", tz="UTC")
    frame = pd.DataFrame(
        {
            "timestamp_utc": ts,
            "close": [100.0 + i * 0.1 for i in range(len(ts))],
        }
    )
    adapter = SimpleNamespace(purpose="RESEARCH")
    calls = {}

    monkeypatch.setattr(
        "market_ai_hub.providers.yfinance_provider.YFinanceProvider.fetch",
        lambda *args, **kwargs: frame,
    )
    monkeypatch.setattr(
        "market_ai_hub.services.model_runtime.get_timesfm_research",
        lambda ack: calls.setdefault("adapter", (ack, adapter))[1],
    )
    monkeypatch.setattr(
        "market_ai_hub.models.timesfm_model.timesfm_forecast",
        lambda used, symbol, closes, horizon, steps: SimpleNamespace(
            model_dump=lambda: {
                "model": "timesfm-3.0",
                "symbol": symbol,
                "warnings": ["TIMESFM3_NON_COMMERCIAL_ONLY"],
                "model_metadata": {
                    "usage_purpose": used.purpose,
                    "serving_allowed": False,
                },
            }
        ),
    )
    monkeypatch.setattr(
        "market_ai_hub.services.forecast_cache.get_cached",
        lambda key: None,
    )
    monkeypatch.setattr(
        "market_ai_hub.services.forecast_cache.set_cached",
        lambda key, value: None,
    )
    result = server.predict_timesfm(
        "^TWII",
        research_usage_ack=TIMESFM3_PERSONAL_RESEARCH_ACK,
    )
    assert calls["adapter"][0] == TIMESFM3_PERSONAL_RESEARCH_ACK
    assert "TIMESFM3_NON_COMMERCIAL_ONLY" in result["warnings"]
    assert result["research_usage"]["usage_mode"] == (
        "PERSONAL_NONCOMMERCIAL_NONPRODUCTION_RESEARCH"
    )
    assert result["research_usage"]["production_use_allowed"] is False
    assert result["research_usage"]["automatic_download_allowed"] is False
