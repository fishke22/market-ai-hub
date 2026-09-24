"""Phase V2-A.2 — factor representation routing tests (synthetic/local only, no network)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from market_ai_hub.research.v2 import factor_representation as FR
from market_ai_hub.research.v2 import session_truth as ST

JST = timezone(timedelta(hours=9))
TPE = timezone(timedelta(hours=8))
CT = timezone(timedelta(hours=-5))

UTC = timezone.utc


def _by_id(reps, rep_id):
    return [r for r in reps if r.representation_id == rep_id][0]


def _daily_obs(factor, rep, asof, value, event_ts, **kw):
    return FR.observe_factor(factor, rep, asof=asof, value=value, event_timestamp=event_ts,
                             timestamp_precision="SESSION_DATE_ONLY", provider="yfinance",
                             source_frequency="DAILY", data_grade="RESEARCH_PROXY", **kw)


# ── §57 factor roles ──
def test_open_venue_without_observation_is_not_live():
    asof = datetime(2026, 9, 24, 20, 0, tzinfo=TPE)
    reps = FR.resolve_factor_representations("TW_INDEX", asof)
    tmf = _by_id(reps, "TMF_FUTURES")
    assert tmf.session.session_status == "AFTER_HOURS_SESSION"
    assert tmf.availability_status == "NOT_AVAILABLE"
    assert tmf.resolved_role == "NOT_AVAILABLE"


def test_fresh_observation_on_closed_cash_market_is_not_direct_live():
    asof = datetime(2026, 9, 24, 20, 0, tzinfo=TPE)
    obs = [FR.observe_factor("TW_INDEX", "TAIEX_CASH", asof=asof, value=23000.0,
                             event_timestamp=datetime(2026, 9, 24, 11, 59, 50, tzinfo=UTC),
                             available_at=datetime(2026, 9, 24, 11, 59, 55, tzinfo=UTC),
                             timestamp_precision="INTRADAY_TIMESTAMP", provider="feed",
                             source_frequency="1M", data_grade="BROKER_REALTIME")]
    reps = FR.resolve_factor_representations("TW_INDEX", asof, observations=obs)
    cash = _by_id(reps, "TAIEX_CASH")
    assert cash.session.market_open is False
    assert cash.resolved_role == "PREVIOUS_SESSION_REFERENCE"
    assert cash.resolved_role not in FR.RESOLVED_ROLE_ORDER[:3]


def test_stale_observation_during_open_market_is_not_live():
    asof = datetime(2026, 9, 24, 7, 0, tzinfo=CT)
    obs = [FR.observe_factor("US_TECH_RISK", "NQ_FUTURES", asof=asof, value=25000.0,
                             event_timestamp=datetime(2026, 9, 24, 6, 0, tzinfo=UTC),
                             available_at=datetime(2026, 9, 24, 6, 0, tzinfo=UTC),
                             timestamp_precision="INTRADAY_TIMESTAMP", provider="broker",
                             source_frequency="1M", data_grade="BROKER_REALTIME",
                             contract_code="NQZ6", series_semantics="CONTRACT", roll_status="NONE")]
    reps = FR.resolve_factor_representations("US_TECH_RISK", asof, observations=obs)
    nq = _by_id(reps, "NQ_FUTURES")
    assert nq.session.market_open is True
    assert nq.resolved_role not in ("DIRECT_LIVE", "LIVE_DERIVATIVE_PROXY", "LIVE_SPOT_PROXY")


def test_daily_yfinance_nq_is_not_live_derivative_proxy():
    asof = datetime(2026, 9, 24, 7, 0, tzinfo=CT)
    obs = [_daily_obs("US_TECH_RISK", "NQ_FUTURES", asof, 25000.0,
                      datetime(2026, 9, 23, 0, 0, tzinfo=UTC),
                      series_semantics="CONTINUOUS", roll_status="UNKNOWN", return_1d=0.01)]
    reps = FR.resolve_factor_representations("US_TECH_RISK", asof, observations=obs)
    nq = _by_id(reps, "NQ_FUTURES")
    assert nq.resolved_role in ("PREVIOUS_SESSION_REFERENCE", "DELAYED_REFERENCE")
    assert nq.return_status == "UNVERIFIED_ROLL"


def test_synthetic_fresh_nq_intraday_can_be_live_derivative_proxy():
    asof = datetime(2026, 9, 24, 7, 0, tzinfo=CT)
    obs = [FR.observe_factor("US_TECH_RISK", "NQ_FUTURES", asof=asof, value=25000.0,
                             event_timestamp=datetime(2026, 9, 24, 11, 59, 50, tzinfo=UTC),
                             available_at=datetime(2026, 9, 24, 11, 59, 55, tzinfo=UTC),
                             timestamp_precision="INTRADAY_TIMESTAMP", provider="broker",
                             source_frequency="1M", data_grade="BROKER_REALTIME",
                             contract_code="NQZ6", series_semantics="CONTRACT", roll_status="NONE")]
    reps = FR.resolve_factor_representations("US_TECH_RISK", asof, observations=obs)
    nq = _by_id(reps, "NQ_FUTURES")
    assert nq.resolved_role == "LIVE_DERIVATIVE_PROXY"
    assert nq.temporal_role == "LIVE"


def test_previous_cash_close_remains_previous_session_reference():
    asof = datetime(2026, 9, 24, 20, 0, tzinfo=JST)
    obs = [_daily_obs("JP_EQUITY", "NIKKEI225_CASH", asof, 40000.0,
                      datetime(2026, 9, 24, 0, 0, tzinfo=UTC))]
    reps = FR.resolve_factor_representations("JP_EQUITY", asof, observations=obs)
    cash = _by_id(reps, "NIKKEI225_CASH")
    assert cash.resolved_role == "PREVIOUS_SESSION_REFERENCE"


def test_cash_and_futures_are_returned_independently():
    asof = datetime(2026, 9, 24, 20, 0, tzinfo=TPE)
    obs = [
        _daily_obs("TW_INDEX", "TAIEX_CASH", asof, 23000.0, datetime(2026, 9, 24, 0, 0, tzinfo=UTC)),
        FR.observe_factor("TW_INDEX", "TMF_FUTURES", asof=asof, value=23010.0,
                          event_timestamp=datetime(2026, 9, 24, 11, 59, 50, tzinfo=UTC),
                          available_at=datetime(2026, 9, 24, 11, 59, 55, tzinfo=UTC),
                          timestamp_precision="INTRADAY_TIMESTAMP", provider="broker",
                          source_frequency="1M", data_grade="BROKER_REALTIME",
                          contract_code="TMF202610", series_semantics="CONTRACT", roll_status="NONE"),
    ]
    reps = FR.resolve_factor_representations("TW_INDEX", asof, observations=obs)
    cash = _by_id(reps, "TAIEX_CASH")
    tmf = _by_id(reps, "TMF_FUTURES")
    assert cash.value == 23000.0 and tmf.value == 23010.0
    assert cash.value != tmf.value  # no fused price
    assert cash.representation_relation == "CASH_REFERENCE"
    assert tmf.representation_relation == "DERIVATIVE_PROXY"


# ── §58 target rules ──
def test_osaka_direct_representation_outranks_cash_proxy_when_available():
    asof = datetime(2026, 9, 24, 11, 0, tzinfo=JST)
    obs = [FR.observe_factor("JP_EQUITY", "OSE_MICRO_FUTURES", asof=asof, value=40000.0,
                             event_timestamp=datetime(2026, 9, 24, 1, 59, 50, tzinfo=UTC),
                             available_at=datetime(2026, 9, 24, 1, 59, 55, tzinfo=UTC),
                             timestamp_precision="INTRADAY_TIMESTAMP", provider="jpx",
                             source_frequency="1M", data_grade="EXCHANGE_REALTIME",
                             contract_code="202612", series_semantics="CONTRACT", roll_status="NONE")]
    reps = FR.resolve_factor_representations("JP_EQUITY", asof, observations=obs)
    assert reps[0].representation_id == "OSE_MICRO_FUTURES"
    assert reps[0].resolved_role == "DIRECT_LIVE"


def test_osaka_cash_proxy_never_becomes_direct_target():
    d = FR.definition_for("JP_EQUITY", "NIKKEI225_CASH")
    assert d.representation_relation == "CASH_REFERENCE"
    assert d.representation_relation != "DIRECT"
    assert d.instrument == "^N225"


def test_taiwan_futures_never_overwrite_taiex_cash_identity():
    asof = datetime(2026, 9, 24, 20, 0, tzinfo=TPE)
    reps = FR.resolve_factor_representations("TW_INDEX", asof)
    cash = _by_id(reps, "TAIEX_CASH")
    assert cash.instrument == "^TWII"
    assert cash.value is None  # not overwritten by any futures price
    assert FR.definition_for("TW_INDEX", "TMF_FUTURES").representation_relation == "DERIVATIVE_PROXY"


def test_index_futures_never_overwrite_taiwan_stock_identity():
    # TAIFEX index futures belong to TW_INDEX context, never to a stock target identity
    assert FR.definition_for_symbol("TMF").economic_factor_id == "TW_INDEX"
    assert FR.definition_for_symbol("TMF").instrument_type == "FUTURE"


# ── §59 cross-representation return ──
def _same_rep_pair():
    asof = datetime(2026, 9, 24, 7, 0, tzinfo=CT)
    a = _daily_obs("US_TECH_RISK", "NQ_FUTURES", asof, 25000.0, datetime(2026, 9, 23, 0, 0, tzinfo=UTC))
    b = _daily_obs("US_TECH_RISK", "NQ_FUTURES", asof, 25250.0, datetime(2026, 9, 24, 0, 0, tzinfo=UTC))
    return a, b


def test_same_representation_return_allowed():
    a, b = _same_rep_pair()
    r, status = FR.representation_return(a, b)
    assert status == "OK"
    assert r is not None and abs(r - 0.01) < 1e-9


def test_cross_representation_return_blocks():
    a = _daily_obs("US_TECH_RISK", "NASDAQ100_CASH", datetime(2026, 9, 24, 7, 0, tzinfo=CT),
                   24000.0, datetime(2026, 9, 23, 0, 0, tzinfo=UTC))
    b = _daily_obs("US_TECH_RISK", "NQ_FUTURES", datetime(2026, 9, 24, 7, 0, tzinfo=CT),
                   25000.0, datetime(2026, 9, 24, 0, 0, tzinfo=UTC))
    r, status = FR.representation_return(a, b)
    assert r is None
    assert status == FR.BLOCKED_CROSS_REPRESENTATION_RETURN


def test_cash_to_futures_return_blocks():
    asof = datetime(2026, 9, 24, 7, 0, tzinfo=CT)
    cash = _daily_obs("US_TECH_RISK", "NASDAQ100_CASH", asof, 24000.0, datetime(2026, 9, 23, 0, 0, tzinfo=UTC))
    fut = _daily_obs("US_TECH_RISK", "NQ_FUTURES", asof, 25000.0, datetime(2026, 9, 24, 0, 0, tzinfo=UTC))
    assert FR.representation_return(cash, fut)[1] == FR.BLOCKED_CROSS_REPRESENTATION_RETURN


def test_futures_to_cash_return_blocks():
    asof = datetime(2026, 9, 24, 7, 0, tzinfo=CT)
    cash = _daily_obs("US_TECH_RISK", "NASDAQ100_CASH", asof, 24000.0, datetime(2026, 9, 23, 0, 0, tzinfo=UTC))
    fut = _daily_obs("US_TECH_RISK", "NQ_FUTURES", asof, 25000.0, datetime(2026, 9, 24, 0, 0, tzinfo=UTC))
    assert FR.representation_return(fut, cash)[1] == FR.BLOCKED_CROSS_REPRESENTATION_RETURN


def test_continuous_future_unknown_roll_marks_return_unverified():
    asof = datetime(2026, 9, 24, 7, 0, tzinfo=CT)
    a = FR.observe_factor("US_TECH_RISK", "NQ_FUTURES", asof=asof, value=25000.0,
                          event_timestamp=datetime(2026, 9, 23, 0, 0, tzinfo=UTC),
                          timestamp_precision="SESSION_DATE_ONLY",
                          series_semantics="CONTINUOUS", roll_status="UNKNOWN")
    b = FR.observe_factor("US_TECH_RISK", "NQ_FUTURES", asof=asof, value=25250.0,
                          event_timestamp=datetime(2026, 9, 24, 0, 0, tzinfo=UTC),
                          timestamp_precision="SESSION_DATE_ONLY",
                          series_semantics="CONTINUOUS", roll_status="UNKNOWN")
    r, status = FR.representation_return(a, b)
    assert r is not None
    assert status == "UNVERIFIED_ROLL"


# ── §60 runtime cross_market entries ──
def _entry(symbol="NQ=F", value=25000.0, ret=0.01):
    asof = datetime(2026, 9, 24, 7, 0, tzinfo=CT)
    return FR.build_cross_market_entry(
        symbol, value=value, return_1d=ret, event_timestamp=datetime(2026, 9, 23, 0, 0, tzinfo=UTC),
        asof=asof, received_at=asof)


def test_cross_market_contains_event_timestamp_or_explicit_unknown():
    e = _entry()
    assert "event_timestamp" in e and e["event_timestamp"] is not None
    e2 = FR.build_cross_market_entry("NOPE", value=1.0, return_1d=0.0, event_timestamp=None,
                                     asof=datetime(2026, 9, 24, tzinfo=UTC))
    assert "event_timestamp" in e2 and e2["event_timestamp"] is None


def test_cross_market_contains_session_status():
    e = _entry()
    assert e["session_status"] in ST.SESSION_STATUSES


def test_cross_market_contains_staleness_status():
    e = _entry()
    assert e["staleness_status"] in ("FRESH", "DELAYED", "STALE", "CLOSED_MARKET_REFERENCE", "UNKNOWN", "NOT_AVAILABLE")


def test_cross_market_contains_representation_id():
    e = _entry()
    assert e["representation_id"] == "NQ_FUTURES"
    assert e["economic_factor_id"] == "US_TECH_RISK"


def test_cross_market_contains_resolved_role():
    e = _entry()
    assert e["resolved_role"] in FR.RESOLVED_ROLES


def test_cross_market_daily_proxy_never_claims_live():
    for symbol in ("NQ=F", "ES=F", "^VIX", "^N225", "^TWII", "USDJPY=X"):
        e = _entry(symbol)
        assert e["resolved_role"] not in ("DIRECT_LIVE", "LIVE_DERIVATIVE_PROXY", "LIVE_SPOT_PROXY"), symbol


def test_cross_market_preserves_last_for_backward_compatibility():
    e = _entry(value=25000.0, ret=0.0123)
    assert e["last"] == 25000.0
    assert e["return_1d"] == 0.0123


# ── §61 packet session/freshness ──
def _packet():
    from market_ai_hub.packet.schema import AnalysisPacket
    p = AnalysisPacket()
    p.price_timestamp = "20200101"  # dated official reference, long stale
    p.target_price_source = "settlement"
    return p


def test_packet_market_session_populated():
    from market_ai_hub.packet.builder import _fill_target_session_truth
    p = _packet()
    _fill_target_session_truth(p, "OSAKA_MICRO")
    assert p.market_session in ST.SESSION_STATUSES


def test_packet_freshness_populated():
    from market_ai_hub.packet.builder import _fill_target_session_truth
    p = _packet()
    _fill_target_session_truth(p, "OSAKA_MICRO")
    assert p.freshness in ("FRESH", "DELAYED", "STALE", "UNKNOWN")


def test_stale_settlement_not_live_verified():
    from market_ai_hub.packet.builder import _fill_target_session_truth
    p = _packet()
    _fill_target_session_truth(p, "OSAKA_MICRO")
    assert p.freshness == "STALE"
    assert p.target_semantics["target_reference_role"] == "DAILY_REFERENCE"
    assert p.target_data_status != "LIVE_VERIFIED"
    assert p.target_semantics["target_data_freshness"]["freshness_status"] == "STALE"


def test_vix_actual_provider_matches_runtime_source():
    from market_ai_hub.packet.builder import _coverage_summary_compact
    entries = {f["factor"]: f for f in _coverage_summary_compact("OSAKA_MICRO")}
    rt = entries["VIX (runtime observation)"]
    assert rt["status"] == "PROXY"
    assert "yfinance" in rt["source"]


# ── §62 regime repairs ──
def _regime_panel():
    idx = pd.date_range("2026-01-01", periods=260, freq="D", tz="UTC")
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "VIX": 15 + rng.normal(0, 2, len(idx)),
        "USDJPY=X": 150 + rng.normal(0, 2, len(idx)),
        "US10Y": 4.0 + rng.normal(0, 0.1, len(idx)),
        "US5Y": 3.8 + rng.normal(0, 0.1, len(idx)),
        "^N225": 40000 + np.cumsum(rng.normal(0, 100, len(idx))),
    }, index=idx)


def _regime():
    from market_ai_hub.regime.engine import MarketRegimeEngine
    return MarketRegimeEngine().compute(_regime_panel())


def test_risk_regime_consumes_canonical_vix_column():
    assert _regime()["risk_regime"]["status"] == "OK"


def test_risk_regime_not_permanently_insufficient_with_valid_vix():
    assert _regime()["risk_regime"]["label"] in ("risk_on", "neutral", "risk_off")


def test_rates_regime_consumes_us10y_us5y():
    assert _regime()["rates_regime"]["status"] == "OK"


def test_rates_regime_metadata_says_10y_5y_not_10y_2y():
    ev = _regime()["rates_regime"]["evidence"]
    assert ev["curve"] == "10Y-5Y"
    assert "us5y" in ev and "us2y" not in ev


def test_rates_regime_not_permanently_insufficient_with_valid_inputs():
    assert _regime()["rates_regime"]["label"] != "insufficient"
