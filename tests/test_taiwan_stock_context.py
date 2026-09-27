from __future__ import annotations

import pandas as pd
import pytest

from market_ai_hub.services.taiwan_stock_context import (
    CONTEXT_SCHEMA_VERSION,
    build_taiwan_stock_context,
    reconcile_context_factor_candidates,
)


class _FakeFinMind:
    def __init__(
        self,
        *,
        fail: str | None = None,
        missing_create_time: bool = False,
        include_future: bool = True,
        future_scale: float = 1.0,
    ):
        self.fail = fail
        self.missing_create_time = missing_create_time
        self.include_future = include_future
        self.future_scale = future_scale
        self.calls: list[str] = []

    def fetch_dataset(self, dataset, data_id="", start_date="", end_date=""):
        self.calls.append(dataset)
        if dataset == self.fail:
            raise RuntimeError("offline")
        if dataset == "TaiwanStockPER":
            rows = [
                {"date": "2026-09-24", "stock_id": "3706", "dividend_yield": 2.5, "PER": 12.0, "PBR": 1.5},
                {"date": "2026-09-24", "stock_id": "2330", "dividend_yield": 1.0, "PER": 99.0, "PBR": 9.0},
            ]
            if self.include_future:
                rows.append(
                    {
                        "date": "2026-09-28",
                        "stock_id": "3706",
                        "dividend_yield": 2.6 * self.future_scale,
                        "PER": 13.0 * self.future_scale,
                        "PBR": 1.6 * self.future_scale,
                    }
                )
            return pd.DataFrame(rows)
        if dataset == "TaiwanStockMonthRevenue":
            rows = [
                {"date": "2025-09-01", "stock_id": "3706", "country": "Taiwan", "revenue": 100.0, "revenue_month": 8, "revenue_year": 2025, "create_time": "2025-09-08"},
                {"date": "2026-08-01", "stock_id": "3706", "country": "Taiwan", "revenue": 110.0, "revenue_month": 7, "revenue_year": 2026, "create_time": "2026-08-10"},
                {"date": "2026-09-01", "stock_id": "3706", "country": "Taiwan", "revenue": 120.0, "revenue_month": 8, "revenue_year": 2026, "create_time": "2026-09-08"},
                {"date": "2026-09-01", "stock_id": "2330", "country": "Taiwan", "revenue": 9999.0, "revenue_month": 8, "revenue_year": 2026, "create_time": "2026-09-08"},
            ]
            if self.include_future:
                rows.append(
                    {
                        "date": "2026-10-01",
                        "stock_id": "3706",
                        "country": "Taiwan",
                        "revenue": 999.0 * self.future_scale,
                        "revenue_month": 9,
                        "revenue_year": 2026,
                        "create_time": "2026-09-29",
                    }
                )
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
        if dataset == "TaiwanStockDividend":
            rows = [
                {
                    "stock_id": "3706",
                    "AnnouncementDate": "2026-01-20",
                    "AnnouncementTime": "14:30:00",
                    "CashExDividendTradingDate": "2026-02-01",
                    "StockExDividendTradingDate": "2026-02-01",
                    "CashEarningsDistribution": 2.0,
                    "StockEarningsDistribution": 0.0,
                }
            ]
            if self.include_future:
                rows.append(
                    {
                        "stock_id": "3706",
                        "AnnouncementDate": "2026-09-28",
                        "AnnouncementTime": "14:30:00",
                        "CashExDividendTradingDate": "2026-10-15",
                        "StockExDividendTradingDate": "",
                        "CashEarningsDistribution": 99.0 * self.future_scale,
                        "StockEarningsDistribution": 0.0,
                    }
                )
            return pd.DataFrame(rows)
        if dataset == "TaiwanStockInstitutionalInvestorsBuySell":
            rows = [
                {"date": "2026-09-24", "stock_id": "3706", "name": "Foreign_Investor", "buy": 1000, "sell": 700},
                {"date": "2026-09-24", "stock_id": "3706", "name": "Investment_Trust", "buy": 100, "sell": 200},
                {"date": "2026-09-24", "stock_id": "3706", "name": "Dealer_self", "buy": 50, "sell": 25},
                {"date": "2026-09-24", "stock_id": "3706", "name": "Dealer_Hedging", "buy": 30, "sell": 40},
                {"date": "2026-09-24", "stock_id": "3706", "name": "Foreign_Dealer_Self", "buy": 10, "sell": 5},
            ]
            if self.include_future:
                rows.append(
                    {
                        "date": "2026-09-28",
                        "stock_id": "3706",
                        "name": "Foreign_Investor",
                        "buy": 9999 * self.future_scale,
                        "sell": 0,
                    }
                )
            return pd.DataFrame(rows)
        if dataset == "TaiwanStockMarginPurchaseShortSale":
            rows = [
                {
                    "date": "2026-09-24",
                    "stock_id": "3706",
                    "MarginPurchaseBuy": 215,
                    "MarginPurchaseCashRepayment": 33,
                    "MarginPurchaseLimit": 331803,
                    "MarginPurchaseSell": 405,
                    "MarginPurchaseTodayBalance": 26575,
                    "MarginPurchaseYesterdayBalance": 26798,
                    "Note": " ",
                    "OffsetLoanAndShort": 0,
                    "ShortSaleBuy": 5,
                    "ShortSaleCashRepayment": 0,
                    "ShortSaleLimit": 331803,
                    "ShortSaleSell": 1,
                    "ShortSaleTodayBalance": 41,
                    "ShortSaleYesterdayBalance": 45,
                }
            ]
            if self.include_future:
                future = dict(rows[0])
                future.update(
                    {
                        "date": "2026-09-28",
                        "MarginPurchaseBuy": 9999 * self.future_scale,
                        "ShortSaleTodayBalance": 999 * self.future_scale,
                    }
                )
                rows.append(future)
            return pd.DataFrame(rows)
        if dataset == "TaiwanStockSecuritiesLending":
            rows = [
                {
                    "date": "2026-09-24",
                    "stock_id": "3706",
                    "transaction_type": "競價",
                    "volume": 20,
                    "fee_rate": 2.5,
                    "close": 78.5,
                    "original_return_date": "2027-03-24",
                    "original_lending_period": 181,
                },
                {
                    "date": "2026-09-24",
                    "stock_id": "3706",
                    "transaction_type": "議借",
                    "volume": 45,
                    "fee_rate": 16.0,
                    "close": 78.5,
                    "original_return_date": "2027-03-24",
                    "original_lending_period": 181,
                },
            ]
            if self.include_future:
                rows.append(
                    {
                        "date": "2026-09-28",
                        "stock_id": "3706",
                        "transaction_type": "議借",
                        "volume": 999 * self.future_scale,
                        "fee_rate": 99.0,
                        "close": 99.0,
                        "original_return_date": "2027-03-28",
                        "original_lending_period": 181,
                    }
                )
            return pd.DataFrame(rows)
        if dataset == "TaiwanStockShareholding":
            rows = [
                {
                    "date": "2026-09-24",
                    "stock_id": "3706",
                    "stock_name": "神達",
                    "InternationalCode": "TW0003706008",
                    "ForeignInvestmentRemainingShares": 1202248163,
                    "ForeignInvestmentShares": 124964305,
                    "ForeignInvestmentRemainRatio": 90.58,
                    "ForeignInvestmentSharesRatio": 9.41,
                    "ForeignInvestmentUpperLimitRatio": 100.0,
                    "ChineseInvestmentUpperLimitRatio": 100.0,
                    "NumberOfSharesIssued": 1327212468,
                    "RecentlyDeclareDate": "2026-04-24",
                    "note": "",
                }
            ]
            if self.include_future:
                future = dict(rows[0])
                future.update(
                    {
                        "date": "2026-09-28",
                        "ForeignInvestmentShares": 999999999 * self.future_scale,
                        "ForeignInvestmentSharesRatio": 99.0,
                    }
                )
                rows.append(future)
            return pd.DataFrame(rows)
        return pd.DataFrame()


class _FakeTWSE:
    def fetch_context_valuation(self):
        return pd.DataFrame(
            [
                {
                    "Date": "1150924",
                    "Code": "3706",
                    "Name": "神達",
                    "PEratio": "12.0",
                    "DividendYield": "2.5",
                    "PBratio": "1.5",
                }
            ]
        )

    def fetch_context_monthly_revenue(self):
        return pd.DataFrame(
            [
                {
                    "出表日期": "1150908",
                    "資料年月": "11508",
                    "公司代號": "3706",
                    "公司名稱": "神達",
                    "營業收入-當月營收": "0.12",
                    "營業收入-上月比較增減(%)": str((120.0 / 110.0 - 1.0) * 100.0),
                    "營業收入-去年同月增減(%)": "20.0",
                }
            ]
        )

    def fetch_context_margin_short(self):
        return pd.DataFrame(
            [
                {
                    "股票代號": "3706",
                    "股票名稱": "神達",
                    "融資買進": "215",
                    "融資賣出": "405",
                    "融資今日餘額": "26575",
                    "融券買進": "5",
                    "融券賣出": "1",
                    "融券今日餘額": "41",
                }
            ]
        )

    def fetch_context_eps_report(self):
        return pd.DataFrame(
            [
                {
                    "出表日期": "1150927",
                    "年度": "115",
                    "季別": "2",
                    "公司代號": "3706",
                    "公司名稱": "神達控股股份有限公司",
                    "基本每股盈餘(元)": "2.58",
                }
            ]
        )


def _context(*, as_of="2026-09-28T00:00:00Z", **kwargs):
    return build_taiwan_stock_context(
        "3706.TW",
        as_of=as_of,
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
    assert flow["values"]["total_net"] == 220.0
    assert flow["values"]["foreign_investor_net"] == 300.0
    assert flow["values"]["investment_trust_net"] == -100.0
    assert flow["values"]["dealer_net"] == 15.0
    assert flow["values"]["foreign_dealer_self_net"] == 5.0
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


def test_dividend_ex_right_context_requires_announcement_known_by_cutoff():
    out = _context()
    dividend = out["channels"]["dividend_ex_right"]
    assert dividend["status"] == "AVAILABLE"
    assert dividend["values"]["CashExDividendTradingDate"] == "2026-02-01"
    assert dividend["values"]["CashEarningsDistribution"] == 2.0
    assert dividend["available_at"].startswith("2026-01-20T06:30:00")
    assert dividend["published_at"] == dividend["available_at"]
    assert dividend["pit_usable"] is True
    assert dividend["predictive_feature_allowed"] is False
    assert dividend["normalization_contract"].endswith(
        "TAIWAN_STOCK_REFERENCE_RESET_CONTINUITY_V1"
    )


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


def test_context_v3_exposes_auditable_factor_metadata_and_source_policy():
    out = _context()
    assert out["schema_version"] == "TAIWAN_STOCK_CONTEXT_V3"
    assert out["source_semantics_version"] == "FINMIND_TWSE_RECEIPT_TARGET_CONTEXT_ASOF_V3"
    assert out["freshness_policy_version"] == "TAIWAN_STOCK_CONTEXT_FRESHNESS_V2"
    assert out["predictive_feature_allowed"] is False
    assert out["source_reconciliation"]["policy"] == "PRESERVE_CONFLICTS_NEVER_AVERAGE"
    assert out["source_reconciliation"]["research_proxy_fallback_allowed"] is False
    factor = out["channels"]["valuation"]["factors"]["pe_ratio"]
    for key in (
        "factor_id",
        "value",
        "units",
        "observation_period",
        "source",
        "source_dataset",
        "published_at",
        "available_at",
        "retrieved_at",
        "cutoff",
        "freshness_seconds",
        "freshness_days",
        "freshness_status",
        "PIT_eligible",
        "predictive_feature_allowed",
        "missing_reason",
        "provenance_hash",
    ):
        assert key in factor
    assert factor["value"] == 12.0
    assert factor["units"] == "RATIO"
    assert factor["source_dataset"] == "TaiwanStockPER"
    assert factor["PIT_eligible"] is True
    assert factor["predictive_feature_allowed"] is False


def test_twse_official_crosscheck_is_receipt_time_only_and_never_averages():
    out = build_taiwan_stock_context(
        "3706.TW",
        as_of="2026-09-27T00:00:00Z",
        finmind=_FakeFinMind(),
        twse=_FakeTWSE(),
        include_twse_official=True,
    )
    official = out["official_source_crosscheck"]
    assert official["schema_version"] == "TWSE_OPENAPI_RECEIPT_CROSSCHECK_V1"
    assert official["historical_backfill_eligible"] is False
    assert official["historical_backfill_reason"] == "RETRIEVED_AFTER_DECISION_CANNOT_BACKDATE"

    valuation = official["channels"]["valuation"]
    assert valuation["observation_date"] == "2026-09-24"
    assert valuation["values"]["pe_ratio"] == 12.0
    assert valuation["comparison_to_active_source"] == "MATCH_SAME_PERIOD_AND_UNITS"

    revenue = official["channels"]["monthly_revenue"]
    assert revenue["observation_period"] == "2026-08"
    assert revenue["values"]["revenue"] == pytest.approx(120.0)
    assert revenue["comparison_to_active_source"] == "MATCH_ON_PERIOD_REVENUE_AND_MOM"
    assert revenue["report_date_is_exact_publication_timestamp"] is False

    margin = official["channels"]["margin_short"]
    assert margin["values"]["MarginPurchaseTodayBalance"] == 26575.0
    assert margin["observation_date"] is None
    assert margin["comparison_to_active_source"] == "NOT_RECONCILED_OBSERVATION_DATE_MISSING"

    eps = official["channels"]["eps_report"]
    assert eps["observation_period"] == "2026-Q2"
    assert eps["values"]["basic_eps"] == 2.58
    assert eps["active_source_value"] == 1.48
    assert eps["comparison_to_active_source"] == "NOT_RECONCILED_REPORT_SEMANTICS_UNVERIFIED"
    assert eps["report_date_is_exact_publication_timestamp"] is False

    assert official["channels"]["institutional_flow"]["status"] == "NOT_AVAILABLE_FREE_OPENAPI"
    assert official["channels"]["securities_lending"]["status"] == "RELATION_MISMATCH_NOT_SUBSTITUTE"
    assert official["channels"]["shareholding"]["status"] == "COVERAGE_MISMATCH_NOT_SUBSTITUTE"
    assert official["channels"]["news"]["status"] == "NOT_AVAILABLE"
    assert out["historical_revision_safe"] is False
    assert out["coverage"]["predictive_experiment_data_ready"] is False


def test_margin_short_lending_and_shareholding_are_cutoff_safe_context_only():
    out = _context()
    margin = out["channels"]["margin_short"]
    assert margin["status"] == "AVAILABLE"
    assert margin["observation_date"] == "2026-09-24"
    assert margin["values"]["MarginPurchaseBuy"] == 215.0
    assert margin["values"]["ShortSaleTodayBalance"] == 41.0
    assert "UNIT_UNSPECIFIED" in margin["factors"]["margin_purchase_buy"]["units"]
    assert margin["factors"]["margin_purchase_buy"]["predictive_feature_allowed"] is False

    lending = out["channels"]["securities_lending"]
    assert lending["status"] == "AVAILABLE"
    assert lending["observation_date"] == "2026-09-24"
    assert lending["values"]["total_volume"] == 65.0
    assert lending["values"]["trade_count"] == 2
    assert lending["values"]["fee_rate_aggregation"] == "NONE_SOURCE_ROWS_PRESERVED"
    assert lending["factors"]["securities_lending_total_volume"]["predictive_feature_allowed"] is False

    shareholding = out["channels"]["shareholding"]
    assert shareholding["status"] == "AVAILABLE"
    assert shareholding["observation_date"] == "2026-09-24"
    assert shareholding["values"]["ForeignInvestmentShares"] == 124964305.0
    assert shareholding["values"]["ForeignInvestmentSharesRatio"] == 9.41
    assert shareholding["factors"]["foreign_investment_shares"]["units"] == "SHARES"


def test_paid_concentration_channel_is_not_queried_or_faked():
    provider = _FakeFinMind()
    out = build_taiwan_stock_context(
        "3706.TW",
        as_of="2026-09-28T00:00:00Z",
        finmind=provider,
    )
    concentration = out["channels"]["shareholding_concentration"]
    assert concentration["status"] == "NOT_AVAILABLE_FREE_TIER"
    assert concentration["pit_usable"] is False
    assert concentration["predictive_feature_allowed"] is False
    assert concentration["factors"]["shareholding_concentration"]["value"] is None
    assert "TaiwanStockHoldingSharesPer" not in provider.calls


def test_future_value_perturbation_cannot_change_past_cutoff_snapshot():
    a = _context(future_scale=1.0)
    b = _context(future_scale=1000.0)
    for channel in (
        "valuation",
        "monthly_revenue",
        "institutional_flow",
        "margin_short",
        "securities_lending",
        "shareholding",
    ):
        assert a["channels"][channel]["observation_date"] == b["channels"][channel]["observation_date"]
        assert a["channels"][channel]["values"] == b["channels"][channel]["values"]


def test_stale_valuation_is_warning_not_predictive_promotion():
    out = _context(as_of="2026-10-10T00:00:00Z", include_future=False)
    valuation = out["channels"]["valuation"]
    assert valuation["freshness_status"] == "STALE"
    assert valuation["factors"]["pe_ratio"]["freshness_status"] == "STALE"
    assert valuation["factors"]["pe_ratio"]["predictive_feature_allowed"] is False


@pytest.mark.parametrize(
    ("left", "right", "reason"),
    [
        (
            {"factor_id": "pe_ratio", "value": 12.0, "units": "RATIO", "observation_period": "2026-09-24", "source_priority_rank": 10},
            {"factor_id": "pe_ratio", "value": 12.0, "units": "PERCENT", "observation_period": "2026-09-24", "source_priority_rank": 20},
            "UNIT_MISMATCH",
        ),
        (
            {"factor_id": "eps", "value": 1.48, "units": "TWD_PER_SHARE", "observation_period": "2026-Q2", "source_priority_rank": 10},
            {"factor_id": "eps", "value": 1.48, "units": "TWD_PER_SHARE", "observation_period": "2026-Q1", "source_priority_rank": 20},
            "PERIOD_MISMATCH",
        ),
        (
            {"factor_id": "pe_ratio", "value": 12.0, "units": "RATIO", "observation_period": "2026-09-24", "source_priority_rank": 10},
            {"factor_id": "pe_ratio", "value": 13.0, "units": "RATIO", "observation_period": "2026-09-24", "source_priority_rank": 20},
            "SOURCE_DISAGREEMENT",
        ),
    ],
)
def test_reconciliation_conflicts_never_average(left, right, reason):
    out = reconcile_context_factor_candidates([left, right])
    assert out["status"] == "CONFLICT"
    assert out["reason"] == reason
    assert out["selected"] is None
    assert out["aggregation"] == "NONE"
    assert len(out["candidates"]) == 2


def test_semantically_equal_sources_use_priority_without_averaging():
    high = {
        "factor_id": "pe_ratio",
        "value": 12.0,
        "units": "RATIO",
        "observation_period": "2026-09-24",
        "source": "official",
        "source_priority_rank": 10,
    }
    low = {
        **high,
        "source": "vendor",
        "source_priority_rank": 20,
    }
    out = reconcile_context_factor_candidates([low, high])
    assert out["status"] == "SELECTED"
    assert out["selected"]["source"] == "official"
    assert out["aggregation"] == "NONE"


def test_news_readiness_never_becomes_probability():
    news = _context()["channels"]["news"]
    assert news["status"] == "NOT_AVAILABLE"
    assert news["values"]["target_news_provider_ready"] is False
    assert news["values"]["event_provider_ready"] is False
    assert news["news_sentiment_probability_allowed"] is False
    assert "probability" not in news["factors"]["target_news_provider_ready"]
