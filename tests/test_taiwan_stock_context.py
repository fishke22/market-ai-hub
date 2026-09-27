from __future__ import annotations

import pandas as pd
import pytest

from market_ai_hub.services.taiwan_stock_context import (
    CONTEXT_SCHEMA_VERSION,
    build_taiwan_stock_context,
)


class _FakeFinMind:
    def __init__(self, *, fail: str | None = None, missing_create_time: bool = False):
        self.fail = fail
        self.missing_create_time = missing_create_time

    def fetch_dataset(self, dataset, data_id="", start_date="", end_date=""):
        if dataset == self.fail:
            raise RuntimeError("offline")
        if dataset == "TaiwanStockPER":
            return pd.DataFrame(
                [
                    {"date": "2026-09-24", "stock_id": "3706", "dividend_yield": 2.5, "PER": 12.0, "PBR": 1.5},
                    {"date": "2026-09-28", "stock_id": "3706", "dividend_yield": 2.6, "PER": 13.0, "PBR": 1.6},
                    {"date": "2026-09-24", "stock_id": "2330", "dividend_yield": 1.0, "PER": 99.0, "PBR": 9.0},
                ]
            )
        if dataset == "TaiwanStockMonthRevenue":
            rows = [
                {"date": "2025-09-01", "stock_id": "3706", "country": "Taiwan", "revenue": 100.0, "revenue_month": 8, "revenue_year": 2025, "create_time": "2025-09-08"},
                {"date": "2026-08-01", "stock_id": "3706", "country": "Taiwan", "revenue": 110.0, "revenue_month": 7, "revenue_year": 2026, "create_time": "2026-08-10"},
                {"date": "2026-09-01", "stock_id": "3706", "country": "Taiwan", "revenue": 120.0, "revenue_month": 8, "revenue_year": 2026, "create_time": "2026-09-08"},
                {"date": "2026-09-01", "stock_id": "2330", "country": "Taiwan", "revenue": 9999.0, "revenue_month": 8, "revenue_year": 2026, "create_time": "2026-09-08"},
                {"date": "2026-10-01", "stock_id": "3706", "country": "Taiwan", "revenue": 999.0, "revenue_month": 9, "revenue_year": 2026, "create_time": "2026-09-29"},
            ]
            frame = pd.DataFrame(rows)
            if self.missing_create_time:
                frame = frame.drop(columns=["create_time"])
            return frame
        if dataset == "TaiwanStockFinancialStatements":
            return pd.DataFrame(
                [
                    {"date": "2026-03-31", "stock_id": "3706", "type": "EPS", "value": 1.1, "origin_name": "基本每股盈餘"},
                    {"date": "2026-06-30", "stock_id": "3706", "type": "EPS", "value": 1.48, "origin_name": "基本每股盈餘"},
                    {"date": "2026-06-30", "stock_id": "3706", "type": "Revenue", "value": 999.0, "origin_name": "營業收入"},
                ]
            )
        if dataset == "TaiwanStockInstitutionalInvestorsBuySell":
            return pd.DataFrame(
                [
                    {"date": "2026-09-24", "stock_id": "3706", "name": "Foreign_Investor", "buy": 1000, "sell": 700},
                    {"date": "2026-09-24", "stock_id": "3706", "name": "Investment_Trust", "buy": 100, "sell": 200},
                    {"date": "2026-09-28", "stock_id": "3706", "name": "Foreign_Investor", "buy": 9999, "sell": 0},
                ]
            )
        return pd.DataFrame()


def _context(**kwargs):
    return build_taiwan_stock_context(
        "3706.TW",
        as_of="2026-09-28T00:00:00Z",
        finmind=_FakeFinMind(**kwargs),
    )


def test_context_uses_conservative_asof_for_daily_valuation_and_flow():
    out = _context()
    valuation = out["channels"]["valuation"]
    flow = out["channels"]["institutional_flow"]

    assert valuation["observation_date"] == "2026-09-24"
    assert valuation["values"]["pe_ratio"] == 12.0
    assert valuation["values"]["pbr"] == 1.5
    assert valuation["available_at"].startswith("2026-09-24T16:00:00")
    assert valuation["pit_usable"] is True

    assert flow["observation_date"] == "2026-09-24"
    assert flow["values"]["total_net"] == 200.0
    assert flow["available_at"].startswith("2026-09-24T16:00:00")
    assert flow["pit_usable"] is True


def test_month_revenue_create_time_controls_asof_and_growth():
    out = _context()
    revenue = out["channels"]["monthly_revenue"]

    assert revenue["status"] == "AVAILABLE"
    assert revenue["values"]["revenue"] == 120.0
    assert revenue["values"]["revenue_year"] == 2026
    assert revenue["values"]["revenue_month"] == 8
    assert revenue["values"]["mom_growth"] == 120.0 / 110.0 - 1.0
    assert revenue["values"]["yoy_growth"] == pytest.approx(0.2)
    assert revenue["available_at"].startswith("2026-09-08T16:00:00")
    assert revenue["pit_usable"] is True


def test_month_revenue_without_create_time_is_nonpit_context():
    out = _context(missing_create_time=True)
    revenue = out["channels"]["monthly_revenue"]

    assert revenue["status"] == "AVAILABLE_NON_PIT_CONTEXT"
    assert revenue["pit_usable"] is False
    assert revenue["available_at"] is None
    assert revenue["availability_semantics"] == "CREATE_TIME_MISSING_PUBLICATION_TIME_UNKNOWN"


def test_month_revenue_missing_create_time_still_filters_future_period_rows():
    out = _context(missing_create_time=True)
    revenue = out["channels"]["monthly_revenue"]

    assert revenue["observation_date"] == "2026-09-01"
    assert revenue["values"]["revenue"] == 120.0
    assert revenue["observation_date"] != "2026-10-01"


def test_eps_period_end_is_not_mislabelled_as_publication_time():
    out = _context()
    eps = out["channels"]["eps"]

    assert eps["status"] == "AVAILABLE_NON_PIT_CONTEXT"
    assert eps["values"]["eps"] == 1.48
    assert eps["observation_date"] == "2026-06-30"
    assert eps["available_at"] is None
    assert eps["pit_usable"] is False
    assert eps["availability_semantics"] == "PERIOD_END_ONLY_PUBLICATION_TIME_UNKNOWN"


def test_channel_failure_isolated_and_news_stays_explicitly_unavailable():
    out = _context(fail="TaiwanStockPER")

    assert out["channels"]["valuation"]["status"] == "REQUEST_FAILED"
    assert out["channels"]["monthly_revenue"]["status"] == "AVAILABLE"
    news = out["channels"]["news"]
    assert news["status"] == "NOT_AVAILABLE"
    assert news["generic_web_news_fallback_allowed"] is False
    assert news["news_sentiment_probability_allowed"] is False


def test_context_contract_never_promotes_to_predictive_feature_or_edge():
    out = _context()

    assert out["schema_version"] == CONTEXT_SCHEMA_VERSION
    assert out["predictive_feature_eligible"] is False
    assert out["historical_revision_safe"] is False
    assert out["coverage"]["predictive_experiment_data_ready"] is False
    assert "eps" in out["coverage"]["nonpit_channels"]
    assert "news" in out["coverage"]["unavailable_channels"]
    assert set(out["coverage"]["missing_or_nonpit_channels"]) >= {"eps", "news"}
    assert out["validation_claims"] == {
        "PREDICTIVE_GAIN": False,
        "CALIBRATED": False,
        "TRADING_EDGE": False,
        "result_role": "TARGET_CONTEXT_ONLY_NOT_PREDICTIVE_FEATURE",
    }
    assert "2330" not in str(out)
