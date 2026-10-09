from __future__ import annotations

import pandas as pd
import pytest

from market_ai_hub.targets.contract import (
    EXECUTION_TARGET,
    instrument_display_name,
    normalize_instrument_alias,
)
from market_ai_hub.targets.jpx_daily import parse_micro_settlement_layout


def test_jnu_aliases_resolve_to_micro_target():
    for value in (
        "JNU",
        "jnu2610",
        "JNUPM2612",
        "大阪微日經",
        "大阪日經微型",
        "大阪日經225微型期貨",
        "日經225微型期貨",
        "Nikkei 225 Micro Futures",
    ):
        assert normalize_instrument_alias(value) == EXECUTION_TARGET
    assert instrument_display_name("JNU") == "大阪日經225微型期貨（JNU）"


def test_public_jpx_layout_parser_promotes_only_verified_settlement():
    layout = """Auction Market
Nikkei 225 Micro Futures
Contract Month
202610  10.08  161100023  64,100  64,855  63,860  64,640  64,640  65,190  64,060  64,940  +  940  58,673  37,894  64,995  7,368
+参考 Nikkei 225
Copyright
"""
    rows = parse_micro_settlement_layout(
        layout,
        trade_date="20260918",
        source_url="https://example.invalid/Daily_Report_OSE_20260918.zip",
        source_hash="abc",
    )
    assert len(rows) == 1
    r = rows[0]
    assert r.product == "Nikkei 225 Micro"
    assert r.contract_month == "202610"
    assert r.date == "2026-09-18"
    assert r.settlement == pytest.approx(64995.0)
    assert r.open is None and r.high is None and r.low is None and r.close is None


def test_public_jpx_zip_accepts_nested_daily_report_directory(monkeypatch):
    import io
    import zipfile

    import market_ai_hub.targets.jpx_daily as jpx

    seen = {}

    def fake_pdf(pdf_bytes, *, trade_date, source_url=""):
        seen["bytes"] = pdf_bytes
        seen["trade_date"] = trade_date
        seen["source_url"] = source_url
        return []

    monkeypatch.setattr(jpx, "parse_micro_settlement_pdf", fake_pdf)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "Daily_Report_OSE_20260803/sif_dyr_20260803.pdf",
            b"%PDF-nested-test",
        )
        zf.writestr(
            "Daily_Report_OSE_20260803/sif_dyr_flex_20260803.pdf",
            b"%PDF-flex-should-not-win",
        )

    out = jpx.parse_micro_settlement_zip(
        buf.getvalue(),
        trade_date="20260803",
        source_url="https://example.invalid/nested.zip",
    )
    assert out == []
    assert seen["bytes"] == b"%PDF-nested-test"
    assert seen["trade_date"] == "20260803"


class _DummyAdapter:
    def __init__(self, shift: float):
        self.shift = shift

    def predict(self, series, horizon: int):
        last = float(series.iloc[-1])
        return {
            "path": {
                "p10": [last + self.shift - 200.0] * horizon,
                "p50": [last + self.shift] * horizon,
                "p90": [last + self.shift + 200.0] * horizon,
            }
        }


def _series_and_meta():
    idx = pd.date_range("2026-08-01", periods=35, freq="B", tz="UTC")
    series = pd.Series([64000.0 + i * 50 for i in range(35)], index=idx)
    meta = {
        "status": "OK",
        "contract_month": "202610",
        "quote_code": "JNU2610",
        "sample_count": len(series),
        "first_date": "2026-08-01",
        "latest_date": "2026-09-18",
        "latest_settlement": float(series.iloc[-1]),
        "source": "JPX/OSE 官方每日報告與清算價",
        "series_semantics": "EXACT_CONTRACT",
        "price_semantics": "SETTLEMENT",
    }
    return series, meta


def test_direct_micro_service_forecasts_exact_contract(monkeypatch):
    import market_ai_hub.services.jnu_direct as d

    monkeypatch.setattr(d, "load_direct_micro_settlements", lambda contract_month="": _series_and_meta())
    monkeypatch.setattr(d, "get_chronos", lambda: _DummyAdapter(300.0))
    monkeypatch.setattr(d, "get_timesfm", lambda: _DummyAdapter(500.0))

    out = d.analyze_jnu_direct("1d")
    assert out["status"] == "OK"
    assert out["direct_model_available"] is True
    assert out["target"] == EXECUTION_TARGET
    assert out["contract_month"] == "202610"
    assert out["scope"] == "DIRECT_MICRO_SETTLEMENT_RESEARCH"
    assert out["forecast_price_type"] == "NEXT_PUBLISHED_SETTLEMENT_OBSERVATION"
    # 2026-09-21..23 are OSE holiday sessions but the next official published
    # settlement observation after the 9/18 row is on the cash-business cadence.
    assert out["target_dates"] == ["2026-09-24"]
    assert out["ensemble"]["p50"] == pytest.approx(_series_and_meta()[0].iloc[-1] + 400.0)
    assert out["calibrated_probability_available"] is False
    assert out["ensemble"]["ensemble_mode"] == "MULTI_MODEL_AVAILABLE_ENSEMBLE"
    assert out["ensemble"]["available_model_count"] == 2


def test_direct_micro_single_model_is_explicitly_degraded(monkeypatch):
    import market_ai_hub.services.jnu_direct as d

    monkeypatch.setattr(d, "load_direct_micro_settlements", lambda contract_month="": _series_and_meta())
    monkeypatch.setattr(d, "get_chronos", lambda: _DummyAdapter(300.0))

    def blocked_timesfm():
        raise RuntimeError("research purpose blocked in this runtime")

    monkeypatch.setattr(d, "get_timesfm", blocked_timesfm)
    out = d.analyze_jnu_direct("1d")
    assert out["status"] == "OK"
    assert out["ensemble"]["ensemble_mode"] == "SINGLE_MODEL_DEGRADED"
    assert out["ensemble"]["available_model_count"] == 1
    assert out["ensemble"]["available_models"] == ["Chronos-2"]
    summary = d.jnu_user_summary(out, calibration_status={"public_calibrated": False})
    assert "單模型可用" in summary["模型組成"]
    assert "不是多模型一致預測" in summary["模型組成"]


def test_next_published_observation_skips_ose_holiday_only_sessions():
    import market_ai_hub.services.jnu_direct as d

    assert d.next_published_settlement_observation_dates("2026-09-18", 1) == ["2026-09-24"]
    assert d.next_published_settlement_observation_dates("2026-09-18", 3) == [
        "2026-09-24",
        "2026-09-25",
        "2026-09-28",
    ]


def test_jnu_public_summary_is_plain_chinese(monkeypatch):
    import market_ai_hub.services.jnu_direct as d

    monkeypatch.setattr(d, "load_direct_micro_settlements", lambda contract_month="": _series_and_meta())
    monkeypatch.setattr(d, "get_chronos", lambda: _DummyAdapter(300.0))
    monkeypatch.setattr(d, "get_timesfm", lambda: _DummyAdapter(500.0))
    out = d.analyze_jnu_direct("1d")
    summary = d.jnu_user_summary(out, calibration_status={"public_calibrated": False})
    text = str(summary)
    for forbidden in (
        "XTKS",
        "EXCHANGE_VERIFIED",
        "NO_ELIGIBLE_ROWS",
        "NOT_AVAILABLE",
        "NEEDS_CONFIG",
        "MISSING",
        "PROXY_ONLY",
        "null",
    ):
        assert forbidden not in text
    assert "大阪日經225微型期貨（JNU）" in text
    assert "官方清算價" in text
    assert "下一筆官方發布的清算價觀測" in text
    assert "下一交易日的官方清算價" not in text
    assert "目前已有 0 筆合格的真實前向機率樣本" in text
    assert "至少要依時間累積 50 筆校準、50 筆驗證、50 筆最終留出樣本" in text




def test_jnu_public_summary_downgrades_failed_historical_models(monkeypatch):
    import market_ai_hub.services.jnu_direct as d

    monkeypatch.setattr(d, "load_direct_micro_settlements", lambda contract_month="": _series_and_meta())
    monkeypatch.setattr(d, "get_chronos", lambda: _DummyAdapter(300.0))
    monkeypatch.setattr(d, "get_timesfm", lambda: _DummyAdapter(500.0))
    out = d.analyze_jnu_direct("1d")
    out["historical_validation"] = {
        "status": "OK",
        "overall": "HISTORICAL_UNVALIDATED",
        "any_model_beats_last_price_naive": False,
        "models": {
            "chronos-2": {
                "paired_vs_last_price_naive": {
                    "common_origin_count": 10,
                    "uncertainty_status": "EXPLORATORY_ONLY",
                    "delta_ci_lower": -1.0,
                    "delta_ci_upper": 2.0,
                }
            },
            "timesfm-3.0": {
                "paired_vs_last_price_naive": {
                    "common_origin_count": 10,
                    "uncertainty_status": "EXPLORATORY_ONLY",
                    "delta_ci_lower": -2.0,
                    "delta_ci_upper": 3.0,
                }
            },
        },
    }
    summary = d.jnu_user_summary(out, calibration_status={"public_calibrated": False, "settled_samples": 0})
    assert summary["直接價格模型"]["可信度"] == "低信心研究參考"
    assert "平均絕對誤差" in summary["歷史驗證"]
    assert "不代表已證明" in summary["歷史驗證"]
    assert "10 個同一批歷史預測樣本" in summary["模型比較可信度"]
    assert "探索性" in summary["模型比較可信度"]
    assert "單日模型方向" in summary["操作參考"]


def test_jnu_public_summary_prefers_sealed_prequential_holdout():
    import market_ai_hub.services.jnu_direct as d

    out = {
        "status": "OK",
        "data": {
            "contract_month": "202610",
            "latest_date": "2026-09-25",
            "latest_settlement": 66140.0,
        },
        "ensemble": {"p10": 65000.0, "p50": 66200.0, "p90": 67400.0, "expected_return": 0.001},
        "research_stance": "NEUTRAL",
        "historical_validation": {"status": "NOT_RUN"},
        "historical_prequential": {
            "status": "OK",
            "origin_count": 131,
            "ensemble": {
                "all": {
                    "paired_vs_last_price_naive": {"delta_ci_lower": 11.0, "delta_ci_upper": 132.0},
                },
                "partitions": {
                    "HISTORICAL_FINAL_HOLDOUT": {
                        "n": 48,
                        "evaluation": {
                            "model": {"mase": 1.12},
                            "beats_naive_mae": False,
                        },
                        "paired_vs_last_price_naive": {
                            "delta_ci_lower": -24.0,
                            "delta_ci_upper": 229.0,
                        },
                    }
                },
            },
        },
    }
    summary = d.jnu_user_summary(out, calibration_status={"public_calibrated": False, "settled_samples": 0})
    assert "131 筆逐日歷史重播" in summary["模型比較可信度"]
    assert "最終區段有 48 筆" in summary["模型比較可信度"]
    assert "訓練資料截止日" in summary["模型比較可信度"]
    assert summary["直接價格模型"]["可信度"] == "低信心研究參考"


def test_analyze_jnu_mcp_refreshes_and_returns_human_view(monkeypatch):
    import market_ai_hub.mcp.server as server
    import market_ai_hub.services.data_continuity as dc
    import market_ai_hub.services.jnu_direct as d

    calls = {"refresh": 0, "validate": None}

    def fake_refresh():
        calls["refresh"] += 1
        return {"status": "OK"}

    direct = {
        "status": "OK",
        "data": {
            "contract_month": "202610",
            "latest_date": "2026-09-25",
            "latest_settlement": 66140.0,
        },
        "ensemble": {"p10": 65000.0, "p50": 66200.0, "p90": 67400.0, "expected_return": 0.001},
        "research_stance": "NEUTRAL",
        "historical_validation": {
            "status": "OK",
            "overall": "HISTORICAL_UNVALIDATED",
            "any_model_beats_last_price_naive": False,
        },
    }

    def fake_analyze(*, horizon, contract_month, validate_history):
        calls["validate"] = validate_history
        return direct

    monkeypatch.setattr(d, "refresh_jnu_direct_data", fake_refresh)
    monkeypatch.setattr(d, "analyze_jnu_direct", fake_analyze)
    monkeypatch.setattr(
        dc,
        "jnu_data_continuity_status",
        lambda contract_month="": {
            "mode": "NORMAL_TARGET_DATA",
            "context_only": False,
            "freshness_status": "FRESH_UNTIL_NEXT_EXPECTED_PUBLICATION",
            "source_redundancy": {"status": "DUAL_CHANNEL_MATCH"},
            "context_confidence_grade": "HIGH",
        },
    )
    monkeypatch.setattr(
        server,
        "get_forward_test_status",
        lambda: {"w32_event_probability_settled": 0},
    )
    out = server.analyze_jnu()
    assert calls == {"refresh": 1, "validate": True}
    assert out["商品"] == "大阪日經225微型期貨（JNU）"
    assert out["直接價格模型"]["可信度"] == "低信心研究參考"
    assert out["資料連續性"]["模式"] == "NORMAL_TARGET_DATA"
    assert "Settlement Forecast" in out["產品分層"]["本工具"]
    assert "analyze_jnu_trading_path" in out["產品分層"]["交易路徑"]
    assert "官方發布的限月清算價" in out["資料來源與錄製說明"]
    assert "analyze_jnu_trading_path" in out["資料來源與錄製說明"]
    assert "status" not in out


def test_analyze_jnu_mcp_normalizes_common_contract_aliases(monkeypatch):
    import market_ai_hub.mcp.server as server
    import market_ai_hub.services.data_continuity as dc
    import market_ai_hub.services.jnu_direct as d

    seen = []
    monkeypatch.setattr(d, "refresh_jnu_direct_data", lambda: {"status": "OK"})

    def fake_continuity(contract_month=""):
        seen.append(("continuity", contract_month))
        return {"mode": "NORMAL_TARGET_DATA", "context_only": False}

    def fake_analyze(*, horizon, contract_month, validate_history):
        seen.append(("direct", contract_month))
        return {"status": "OK"}

    monkeypatch.setattr(dc, "jnu_data_continuity_status", fake_continuity)
    monkeypatch.setattr(d, "analyze_jnu_direct", fake_analyze)

    for alias in ("2612", "202612", "JNU2612", "JNUPM2612"):
        seen.clear()
        out = server.analyze_jnu(contract_month=alias, view="audit")
        assert out["status"] == "OK"
        assert seen == [("continuity", "202612"), ("direct", "202612")]


def test_analyze_jnu_mcp_continuity_mode_does_not_call_direct_model(monkeypatch):
    import market_ai_hub.mcp.server as server
    import market_ai_hub.services.data_continuity as dc
    import market_ai_hub.services.jnu_direct as d

    calls = {"direct": 0}
    monkeypatch.setattr(d, "refresh_jnu_direct_data", lambda: {"status": "OK"})

    def forbidden_direct(**kwargs):
        calls["direct"] += 1
        raise AssertionError("direct model must not run in DATA_CONTINUITY_MODE")

    monkeypatch.setattr(d, "analyze_jnu_direct", forbidden_direct)
    monkeypatch.setattr(
        dc,
        "jnu_data_continuity_status",
        lambda contract_month="": {
            "mode": "DATA_CONTINUITY_MODE",
            "context_only": True,
            "reason": "EXPECTED_PUBLISHED_OBSERVATION_OVERDUE",
        },
    )
    monkeypatch.setattr(
        dc,
        "jnu_continuity_user_summary",
        lambda snapshot: {
            "商品": "大阪日經225微型期貨（JNU）",
            "模式": "資料連續性模式（只做情境與風險分析）",
            "PREDICTIVE_GAIN": False,
            "CALIBRATED": False,
            "TRADING_EDGE": False,
        },
    )
    out = server.analyze_jnu()
    assert calls["direct"] == 0
    assert out["模式"].startswith("資料連續性模式")
    assert out["PREDICTIVE_GAIN"] is False

def test_analysis_packet_accepts_jnu_alias(monkeypatch):
    import market_ai_hub.packet.builder as builder
    import market_ai_hub.mcp.server as server

    seen = {}

    def fake_build(**kwargs):
        seen.update(kwargs)
        return {"execution_target": kwargs["target"]}

    monkeypatch.setattr(builder, "build_analysis_packet", fake_build)
    out = server.get_analysis_packet(target="JNU")
    assert out["execution_target"] == EXECUTION_TARGET
    assert seen["target"] == EXECUTION_TARGET


def test_validate_history_degrades_when_a_model_is_governance_blocked(monkeypatch):
    """TimesFM-3 weights are RESEARCH-only; the serving historical-validation loop must
    record the model UNAVAILABLE and keep validating with the remaining models instead of
    raising and taking the whole analysis packet down."""
    import numpy as np

    from market_ai_hub.services import jnu_direct as jd
    from market_ai_hub.services.model_governance import ModelUsageBlocked

    n = jd.DIRECT_VALIDATION_HISTORY_LEN + jd.DIRECT_VALIDATION_ORIGINS + 5
    idx = pd.date_range("2026-05-01", periods=n, freq="D", tz="UTC")
    series = pd.Series([60000.0 + i for i in range(n)], index=idx)
    meta = {"status": "OK", "quote_code": "JNU2610", "contract_month": "202610",
            "latest_date": str(idx[-1].date()), "latest_settlement": float(series.iloc[-1])}
    monkeypatch.setattr(jd, "load_direct_micro_settlements", lambda cm="": (series, meta))

    class _Ok:
        def predict(self, ctx, horizon=1):
            last = float(np.asarray(ctx, dtype=float)[-1])
            return {"path": {"p50": [last], "p10": [last * 0.99], "p90": [last * 1.01]}}

    class _GovernanceBlocked:
        def predict(self, ctx, horizon=1):
            raise ModelUsageBlocked(
                "timesfm-3.0: PURPOSE_SERVING_NOT_ALLOWED (allowed=['RESEARCH'])")

    monkeypatch.setattr(jd, "get_chronos", lambda: _Ok())
    monkeypatch.setattr(jd, "get_timesfm", lambda: _GovernanceBlocked())

    out = jd.validate_jnu_direct_history("202610", force=True)
    assert out["status"] == "OK"
    avail = {row["model"]: row for row in out["model_availability"]}
    assert avail["chronos-2"]["status"] == "AVAILABLE"
    assert avail["timesfm-3.0"]["status"] == "UNAVAILABLE"
    assert avail["timesfm-3.0"]["reason"] == "ModelUsageBlocked"
    assert out["models"]["timesfm-3.0"]["status"] == "MODEL_UNAVAILABLE"
    assert out["models"]["timesfm-3.0"]["mase"] is None
    assert out["overall"] == "HISTORICAL_UNVALIDATED"
    assert out["all_models_beat_last_price_naive"] is False


def test_explicit_contract_month_assigns_contract_source(monkeypatch):
    """#98 regression: 以非空 contract_month 呼叫 load_direct_micro_settlements
    不應拋 UnboundLocalError，且 meta.contract_source 應為 EXPLICIT_ARGUMENT。"""
    from market_ai_hub.services import jnu_direct as jd
    from market_ai_hub.targets.jpx_daily import JPXOSEDailyReportProvider

    daily = pd.DataFrame([{
        "product": "Nikkei 225 Micro",
        "contract_month": "202612",
        "date": "20261009",
        "open": None, "high": None, "low": None, "close": None,
        "volume": None, "settlement": 65000.0,
        "source_url": "https://example.invalid/test",
        "source_hash": "abc123",
    }])
    monkeypatch.setattr(
        JPXOSEDailyReportProvider, "load",
        lambda self, product="": daily,
    )
    monkeypatch.setattr(jd, "_current_settlement_frame",
                        lambda: pd.DataFrame())

    series, meta = jd.load_direct_micro_settlements("202612")
    assert meta["contract_source"] == "EXPLICIT_ARGUMENT"
    assert meta["contract_month"] == "202612"
    assert meta["status"] == "OK"
    assert len(series) == 1
