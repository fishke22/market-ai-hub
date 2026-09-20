"""Phase 2G.1 — true target + official data coverage tests。"""
from datetime import datetime, timezone

import pandas as pd
import pytest

from market_ai_hub.targets.contract import (
    EXECUTION_TARGET,
    TARGET,
    TargetInstrumentContract,
    is_execution_target,
    role_of,
)
from market_ai_hub.targets.coverage import (
    AUTHORITATIVE,
    MISSING,
    DataCoverageAuditor,
)
from market_ai_hub.targets.continuous import ContinuousFuturesBuilder, UNADJUSTED
from market_ai_hub.targets.events import OfficialEvent, event_available, event_visible, official_event_providers
from market_ai_hub.targets.jpx_daily import (
    MICRO_LISTING_DATE,
    MicroListingError,
    JPXOSEDailyReportProvider,
    assert_micro_not_before,
    parse_daily_report,
)
from market_ai_hub.targets.semantics import (
    DIRECT_MICRO_MODEL,
    PROXY_TRAINED_MICRO_ANCHORED,
    MicroForecastSemantics,
)
from market_ai_hub.targets.backtest_contract import (
    FORECAST_EVALUATION,
    STRATEGY_BACKTEST,
    evaluation_kind,
)


# --- 1: true target ---
def test_micro_target_identity():
    assert EXECUTION_TARGET == "OSE_NIKKEI225_MICRO_FUTURES"
    assert is_execution_target("OSE_NIKKEI225_MICRO_FUTURES")
    c = TargetInstrumentContract()
    assert c.execution_target == EXECUTION_TARGET


def test_proxy_not_target():
    assert role_of("^N225") != TARGET
    assert not is_execution_target("^N225")
    assert is_execution_target("OSE_NIKKEI225_MICRO_FUTURES")


# --- 2: JPX parser ---
def test_jpx_micro_parser():
    raw = (
        "product,contract_month,date,open,high,low,close,volume,settlement\n"
        "Nikkei 225 Micro,2024-06,2024-05-01,38000,38500,37900,38300,1000,38300\n"
        "Nikkei 225 Mini,2024-06,2024-05-01,38050,38550,37950,38350,200,38350\n"
        "Other Product,2024-06,2024-05-01,1,2,1,2,0,2\n"
    )
    rows = parse_daily_report(raw)
    assert len(rows) == 2  # 第三列 product 不在 PRODUCT_ROLES → 略過
    assert rows[0].product == "Nikkei 225 Micro" and rows[0].close == 38300.0


def test_no_fake_pre2023_micro():
    with pytest.raises(MicroListingError):
        assert_micro_not_before("2023-05-28")
    assert_micro_not_before("2023-05-29")  # 上市日 OK
    # parser 直接跳過上市前 Micro（不偽造）
    raw = ("product,contract_month,date,open,high,low,close,volume,settlement\n"
           "Nikkei 225 Micro,2023-05,2023-05-28,1,2,1,2,0,2\n"
           "Nikkei 225 Micro,2023-06,2023-05-29,1,2,1,2,0,2\n")
    rows = parse_daily_report(raw)
    assert [r.date for r in rows] == ["2023-05-29"]


def test_jpx_incremental_clamps_micro(tmp_path):
    p = JPXOSEDailyReportProvider(data_root=tmp_path)
    fetched = {}

    def fake_fetcher(s, e):
        fetched["s"] = s
        return "product,contract_month,date,open,high,low,close,volume,settlement\n"

    # 早於上市日的起點會被 clamp 到上市日
    p.download_incremental(fake_fetcher, "2023-01-01", "2023-06-30", product="Nikkei 225 Micro")
    assert fetched["s"] == MICRO_LISTING_DATE.isoformat()


# --- 3: continuous ---
def test_continuous_roll_provenance():
    rows = [
        {"contract_month": "2024-06", "date": "2024-05-01", "close": 38000.0},
        {"contract_month": "2024-06", "date": "2024-05-02", "close": 38100.0},
        {"contract_month": "2024-09", "date": "2024-05-03", "close": 38200.0},
    ]
    b = ContinuousFuturesBuilder(roll_method="last_trading_day", adjustment_method=UNADJUSTED)
    cs = b.build(rows)
    assert cs.roll_method == "last_trading_day"
    assert cs.adjustment_method == UNADJUSTED
    assert cs.roll_dates == ["2024-05-03"]  # 合約月改變 → roll
    assert all(r["is_executable_price"] for r in cs.series)  # unadjusted = 可成交


# --- 4: micro semantics ---
def test_proxy_trained_label():
    s = MicroForecastSemantics()
    assert s.label(has_micro_actual=False) == PROXY_TRAINED_MICRO_ANCHORED
    assert s.label(has_micro_actual=True) == DIRECT_MICRO_MODEL
    assert s.anchor(0.01, 38000.0) == pytest.approx(38380.0)


# --- 6: event information cutoff ---
def test_event_information_cutoff():
    now = datetime(2024, 6, 15, tzinfo=timezone.utc)
    events = [
        OfficialEvent(event_name="CPI", scheduled_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
                      released_at=datetime(2024, 6, 12, tzinfo=timezone.utc), source="BLS",
                      importance_class="HIGH"),
        OfficialEvent(event_name="FOMC", scheduled_at=datetime(2024, 6, 20, tzinfo=timezone.utc),
                      released_at=None, source="FED", importance_class="HIGH"),
    ]
    assert event_available(events[0]) and not event_available(events[1])
    cutoff = datetime(2024, 6, 11, tzinfo=timezone.utc)  # 早於 CPI release
    visible = event_visible(events, cutoff)
    assert visible == []  # CPI released 6/12 > cutoff；FOMC 未 release
    visible2 = event_visible(events, now)
    assert [e.event_name for e in visible2] == ["CPI"]


def test_event_providers_registry():
    providers = official_event_providers()
    assert "BLS" in providers and "CBOE" in providers and "EDINET" in providers
    assert providers["EDINET"].status == "CONFIG_ONLY"


# --- 7: coverage audit ---
def test_coverage_audit():
    recs = DataCoverageAuditor().audit()
    assert len(recs) == 28
    # 不得宣稱全部 authoritative
    assert DataCoverageAuditor().authoritative_count(recs) < len(recs)


# --- 8: backtest contract separation ---
def test_forecast_vs_strategy_backtest_separation():
    assert evaluation_kind(False) == FORECAST_EVALUATION
    assert evaluation_kind(True) == STRATEGY_BACKTEST
    from market_ai_hub.targets.backtest_contract import NautilusTraderAdapter
    assert NautilusTraderAdapter.live_execution_enabled is False
