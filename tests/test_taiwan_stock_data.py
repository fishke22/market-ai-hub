from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
import pytest

from market_ai_hub.providers.base import ProviderInfo, ProviderStatus
from market_ai_hub.services.taiwan_stock_data import (
    ADJUSTMENT_SEMANTICS,
    TaiwanStockDataIntegrityError,
    apply_reference_resets,
    load_taiwan_stock_model_data,
)


def _raw(closes, start="2026-09-07"):
    dates = pd.date_range(start, periods=len(closes), freq="D", tz="Asia/Taipei")
    vals = [float(x) for x in closes]
    return pd.DataFrame(
        {
            "timestamp_utc": dates.tz_convert("UTC"),
            "timestamp_local": dates,
            "symbol": "3706",
            "open": vals,
            "high": [x + 1 for x in vals],
            "low": [x - 1 for x in vals],
            "close": vals,
            "volume": 1000.0,
            "provider": "test",
            "data_grade": "OFFICIAL_DAILY",
        }
    )


def _reset(event_date, before, reference, event_type="EX_RIGHT_DIVIDEND"):
    return {
        "event_type": event_type,
        "event_date": event_date,
        "announcement_at": "2026-08-24",
        "available_at": "2026-08-24",
        "available_at_semantics": "ANNOUNCEMENT_TIME",
        "before_price": float(before),
        "reference_price": float(reference),
        "adjustment_factor": float(before) / float(reference),
        "source": "FinMind:test",
        "source_hash": "abc",
        "adjustment_method": "FORWARD_MULTIPLY_FROM_EFFECTIVE_DATE",
        "adjustment_status": "VERIFIED_REFERENCE_RESET",
        "usable_as_predictive_feature": False,
    }


def test_3706_20260909_corporate_action_golden_removes_mechanical_drop():
    raw = _raw([90.0, 91.3, 81.8, 82.2])
    event = _reset("2026-09-09", 91.3, 80.27, "EX_RIGHT_DIVIDEND:權息")
    adjusted, ledger = apply_reference_resets(raw, [event])

    raw_return = 81.8 / 91.3 - 1
    economic_return = adjusted.loc[2, "close"] / adjusted.loc[1, "close"] - 1

    assert raw_return < -0.10
    assert economic_return == pytest.approx(81.8 / 80.27 - 1, abs=1e-12)
    assert economic_return > 0
    assert adjusted.loc[0, "close"] == raw.loc[0, "close"]
    assert adjusted.loc[1, "close"] == raw.loc[1, "close"]
    assert adjusted.loc[2, "adjustment_factor"] == pytest.approx(91.3 / 80.27)
    assert ledger[0]["event_date"] == "2026-09-09"


@pytest.mark.parametrize(
    ("event_type", "before", "reference"),
    [
        ("CASH_DIVIDEND", 100.0, 97.0),
        ("STOCK_DIVIDEND", 100.0, 90.0),
        ("STOCK_SPLIT", 100.0, 50.0),
        ("STOCK_REVERSE_SPLIT", 50.0, 100.0),
        ("CAPITAL_REDUCTION", 100.0, 80.0),
    ],
)
def test_reference_reset_event_types_preserve_economic_continuity(
    event_type, before, reference
):
    raw = _raw([before, reference, reference * 1.01], start="2026-01-01")
    event = _reset("2026-01-02", before, reference, event_type)
    adjusted, _ = apply_reference_resets(raw, [event])
    assert adjusted.loc[0, "close"] == pytest.approx(before)
    assert adjusted.loc[1, "close"] == pytest.approx(before)
    assert adjusted.loc[2, "close"] == pytest.approx(before * 1.01)


def test_future_event_does_not_mutate_pre_event_history():
    raw = _raw([100, 101, 102, 50, 51], start="2026-01-01")
    event = _reset("2026-01-04", 102, 50, "STOCK_SPLIT")
    adjusted, _ = apply_reference_resets(raw, [event])
    pd.testing.assert_series_equal(
        adjusted.loc[:2, "close"].reset_index(drop=True),
        raw.loc[:2, "close"].reset_index(drop=True),
        check_names=False,
    )


def test_conflicting_same_day_reference_resets_fail_closed():
    raw = _raw([100, 90, 91], start="2026-01-01")
    a = _reset("2026-01-02", 100, 90, "EVENT_A")
    b = _reset("2026-01-02", 100, 80, "EVENT_B")
    with pytest.raises(TaiwanStockDataIntegrityError, match="AMBIGUOUS"):
        apply_reference_resets(raw, [a, b])


class _FakeFinMind:
    def __init__(self, *, raw_fails=False, event_failure=None):
        self.raw_fails = raw_fails
        self.event_failure = event_failure
        self.calls = []

    def status(self):
        return ProviderInfo(name="finmind", status=ProviderStatus.OK)

    def fetch_price(self, symbol, start_date, end_date, adjusted=True):
        self.calls.append(("price", symbol, start_date, end_date, adjusted))
        if self.raw_fails:
            raise RuntimeError("raw unavailable")
        return _raw(list(range(100, 170)), start="2026-01-01")

    def fetch_dataset(self, dataset, data_id="", start_date="", end_date="", timeout=30):
        self.calls.append((dataset, data_id, start_date, end_date))
        if dataset == self.event_failure:
            raise RuntimeError("event channel down")
        if dataset == "TaiwanStockDividendResult":
            return pd.DataFrame(
                [
                    {
                        "date": "2026-02-01",
                        "stock_id": "3706",
                        "before_price": 130.0,
                        "reference_price": 120.0,
                        "after_price": 120.0,
                        "stock_or_cache_dividend": "權息",
                    }
                ]
            )
        if dataset == "TaiwanStockDividend":
            return pd.DataFrame(
                [
                    {
                        "stock_id": "3706",
                        "CashExDividendTradingDate": "2026-02-01",
                        "StockExDividendTradingDate": "2026-02-01",
                        "AnnouncementDate": "2026-01-20",
                        "AnnouncementTime": "14:30:00",
                    }
                ]
            )
        return pd.DataFrame()


class _FakeTWSE:
    def __init__(self):
        self.calls = []

    def fetch_symbol_daily(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        return _raw(list(range(100, 170)), start="2026-01-01")


def test_raw_fallback_keeps_requested_history_window_and_still_adjusts():
    fm = _FakeFinMind(raw_fails=True)
    tw = _FakeTWSE()
    bundle = load_taiwan_stock_model_data(
        "3706.TW",
        "2025-01-01",
        "2026-09-27",
        finmind=fm,
        twse=tw,
    )
    assert tw.calls == [("3706", "20250101", "20260927")]
    assert bundle.metadata["raw_price_source"] == "twse:STOCK_DAY"
    assert bundle.metadata["model_data_grade"] == "OFFICIAL_DAILY"
    assert bundle.metadata["raw_source_is_exchange_official"] is True
    assert bundle.metadata["corporate_action_integrity"] == "CORPORATE_ACTION_NORMALIZED"
    assert bundle.metadata["adjustment_semantics"] == ADJUSTMENT_SEMANTICS
    assert bundle.metadata["event_count"] == 1


def test_finmind_raw_is_not_relabelled_exchange_official():
    bundle = load_taiwan_stock_model_data(
        "3706.TW",
        "2025-01-01",
        "2026-09-27",
        finmind=_FakeFinMind(raw_fails=False),
        twse=_FakeTWSE(),
    )
    assert bundle.metadata["raw_price_source"] == "finmind:TaiwanStockPrice"
    assert bundle.metadata["model_data_grade"] == "RESEARCH_PROXY"
    assert bundle.metadata["raw_source_is_exchange_official"] is False


def test_any_required_reference_channel_failure_blocks_model_data():
    fm = _FakeFinMind(event_failure="TaiwanStockSplitPrice")
    with pytest.raises(
        TaiwanStockDataIntegrityError,
        match="CORPORATE_ACTION_REFERENCE_CHANNEL_INCOMPLETE",
    ):
        load_taiwan_stock_model_data(
            "3706",
            "2025-01-01",
            "2026-09-27",
            finmind=fm,
            twse=_FakeTWSE(),
        )


def test_analyze_taiwan_stock_exposes_raw_current_basis_reference(monkeypatch):
    import market_ai_hub.services.analysis as analysis

    bundle = load_taiwan_stock_model_data(
        "3706.TW",
        "2025-01-01",
        "2026-09-27",
        finmind=_FakeFinMind(raw_fails=False),
        twse=_FakeTWSE(),
    )
    monkeypatch.setattr(analysis, "load_taiwan_stock_model_data", lambda *a, **k: bundle)
    monkeypatch.setattr(analysis, "get_chronos", lambda: object())
    monkeypatch.setattr(analysis, "get_timesfm", lambda: object())
    monkeypatch.setattr(analysis, "chronos_forecast", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("off")))
    monkeypatch.setattr(analysis, "timesfm_forecast", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("off")))
    monkeypatch.setattr(analysis, "baseline_forecast", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("off")))

    out = analysis.analyze_taiwan_stock("3706.TW", "1d")

    assert out["status"] == "OK"
    assert out["reference_price"] == bundle.metadata["raw_latest_close"]
    assert out["reference_price_type"] == "CLOSE"
    assert out["reference_price_source"] == "finmind:TaiwanStockPrice"
    assert out["reference_data_grade"] == "RESEARCH_PROXY"
    assert out["price_basis"] == "RAW_CURRENT_BASIS"


def test_analyze_taiwan_stock_stops_before_models_when_integrity_blocks(monkeypatch):
    import market_ai_hub.services.analysis as analysis

    def blocked(*args, **kwargs):
        raise TaiwanStockDataIntegrityError(
            "CORPORATE_ACTION_REFERENCE_CHANNEL_INCOMPLETE",
            details={"TaiwanStockSplitPrice": "REQUEST_FAILED"},
        )

    model_called = {"value": False}

    def forbidden_model(*args, **kwargs):
        model_called["value"] = True
        raise AssertionError("model must not run after data-integrity failure")

    monkeypatch.setattr(analysis, "load_taiwan_stock_model_data", blocked)
    monkeypatch.setattr(analysis, "chronos_forecast", forbidden_model)
    monkeypatch.setattr(analysis, "baseline_forecast", forbidden_model)

    out = analysis.analyze_taiwan_stock("3706.TW", "4d")
    assert out["status"] == "DATA_INTEGRITY_BLOCKED"
    assert out["data_integrity"]["status"] == "BLOCKED"
    assert out["data_integrity"]["corporate_action_integrity"] == "CORPORATE_ACTION_ADJUSTMENT_UNAVAILABLE"
    assert model_called["value"] is False
