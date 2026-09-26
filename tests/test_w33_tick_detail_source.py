"""W3.3 Yuanta GetStkTickDetail source contract — offline only."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import threading

import pytest

from market_ai_hub.integrations.yuanta.spark_runtime import SparkRuntime
from market_ai_hub.research.v2 import prediction_audit as PA
from market_ai_hub.research.v2 import tick_detail_source as TD

UTC = timezone.utc


def _dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


class _Row:
    def __init__(self, ts, price=42000.0, vol=1, seq=1):
        self.TimeStamp = ts
        self.DealPrice = price
        self.DealVol = vol
        self.BuyPrice = price - 5
        self.SellPrice = price + 5
        self.SeqNo = seq
        self.InOutFlag = 1


class _Result:
    def __init__(self, market=207, stock="JNU2612", rows=None):
        self.MarketNo = market
        self.StockCode = stock
        self.StickDetailList = list(rows or [])


class _DotNetDate:
    Year = 2026
    Month = 9
    Day = 24
    Hour = 15
    Minute = 45
    Second = 0
    Millisecond = 123


def test_schema_is_bound_into_prediction_audit_versions():
    assert TD.W3_TICK_DETAIL_SOURCE_SCHEMA_VERSION == "W3.3"
    assert PA.v2_schema_versions()["tick_detail_source"] == "W3.3"


def test_parse_official_tick_detail_shape_preserves_naive_timestamp_basis():
    obj = _Result(rows=[
        _Row(datetime(2026, 9, 24, 15, 44, 59), 41990.0, seq=2),
        _Row(_DotNetDate(), 42000.0, seq=3),
    ])
    batch = TD.parse_tick_detail_result(obj, received_at=_dt(24, 6, 50))
    assert batch.market_no == 207
    assert batch.stock_code == "JNU2612"
    assert len(batch.rows) == 2
    assert batch.rows[-1].raw_timestamp == datetime(2026, 9, 24, 15, 45, 0, 123000)
    assert batch.rows[-1].raw_timestamp.tzinfo is None
    assert batch.timestamp_basis_status == TD.TIMESTAMP_BASIS_UNVERIFIED
    assert batch.source_snapshot_id.startswith("w33_tick_")


def test_parse_is_deterministic_for_same_payload():
    obj = _Result(rows=[_Row(datetime(2026, 9, 24, 15, 45), 42000.0, seq=10)])
    a = TD.parse_tick_detail_result(obj, received_at=_dt(24, 6, 50))
    b = TD.parse_tick_detail_result(obj, received_at=_dt(24, 6, 50))
    assert a.source_snapshot_id == b.source_snapshot_id


def test_raw_snapshot_identity_excludes_verification_state():
    batch = TD.parse_tick_detail_result(
        _Result(rows=[_Row(datetime(2026, 9, 24, 15, 45), 42000.0, seq=10)]),
        received_at=_dt(24, 6, 50),
    )
    assert "timestamp_basis_status" not in batch.identity_payload()
    assert TD.canonical_tick_detail_snapshot_id(batch) == batch.source_snapshot_id


def test_invalid_nonfinite_tick_rejected():
    with pytest.raises(ValueError):
        TD.parse_tick_detail_result(
            _Result(rows=[_Row(datetime(2026, 9, 24, 15, 45), float("nan"))]),
            received_at=_dt(24, 6, 50),
        )


def test_ose_close_query_window_only_post_close_pre_night():
    ready = TD.ose_close_query_window(_dt(24, 6, 50))  # 15:50 JST
    early = TD.ose_close_query_window(_dt(24, 6, 44))  # 15:44 JST
    late = TD.ose_close_query_window(_dt(24, 8, 0))    # 17:00 JST
    assert ready["status"] == TD.STATUS_QUERY_WINDOW_READY
    assert ready["trading_date"] == "2026-09-24"
    assert early["status"] == TD.STATUS_QUERY_WINDOW_BLOCKED
    assert "DAY_SESSION_NOT_CLOSED" in early["reason"]
    assert late["status"] == TD.STATUS_QUERY_WINDOW_BLOCKED
    assert "NIGHT_SESSION_ALREADY_STARTED" in late["reason"]


def test_weekend_query_window_blocked():
    # 2026-09-26 Saturday
    status = TD.ose_close_query_window(_dt(26, 6, 50))
    assert status["status"] == TD.STATUS_QUERY_WINDOW_BLOCKED
    assert "NOT_OSE_SESSION_DATE" in status["reason"]


def test_terminal_candidate_stays_blocked_until_runtime_timezone_verification():
    batch = TD.parse_tick_detail_result(
        _Result(rows=[_Row(datetime(2026, 9, 24, 15, 45), 42000.0, seq=10)]),
        received_at=_dt(24, 6, 50),
    )
    status = TD.assess_ose_terminal_trade_candidate(batch, request_time=_dt(24, 6, 50))
    assert status["status"] == TD.STATUS_CANDIDATE_BLOCKED
    assert "RUNTIME_VERIFICATION_EVIDENCE_REQUIRED" in status["reason"]
    assert status["terminal_close_materialization_allowed"] is False
    assert status["values_exposed"] is False
    assert "deal_price" not in status


def test_wrong_market_or_symbol_blocks_candidate():
    batch = TD.parse_tick_detail_result(
        _Result(market=203, stock="NQ2612",
                rows=[_Row(datetime(2026, 9, 24, 15, 45), 20000.0)]),
        received_at=_dt(24, 6, 50),
    )
    status = TD.assess_ose_terminal_trade_candidate(batch, request_time=_dt(24, 6, 50))
    assert "MARKET_NOT_OSE" in status["reason"]
    assert "NOT_JNU_CONTRACT" in status["reason"]


def test_no_trade_rows_blocks_candidate():
    batch = TD.parse_tick_detail_result(_Result(rows=[]), received_at=_dt(24, 6, 50))
    status = TD.assess_ose_terminal_trade_candidate(batch, request_time=_dt(24, 6, 50))
    assert "NO_VALID_TRADE_ROWS" in status["reason"]


def test_runtime_verification_contract_exposes_no_values():
    req = TD.runtime_verification_requirements()
    assert req["current_timestamp_basis_status"] == TD.TIMESTAMP_BASIS_UNVERIFIED
    assert req["terminal_close_materialization_allowed"] is False
    assert req["max_last_count"] == 20
    assert req["values_exposed"] is False


class _EnumFactory:
    def __call__(self, value):
        return ("enum", int(value))


class _Lang:
    UTF8 = "UTF8"


class _FakeApi:
    def __init__(self):
        self.calls = []

    def GetStkTickDetail(self, *args):
        self.calls.append(args)
        return True


def _runtime_for_query():
    rt = object.__new__(SparkRuntime)
    rt._api = _FakeApi()
    rt.enumMarketType = _EnumFactory()
    rt.enumStkTickSelectType = _EnumFactory()
    rt.enumLangType = _Lang()
    return rt


def test_spark_runtime_typed_tick_detail_request_is_bounded_and_read_only():
    rt = _runtime_for_query()
    accepted = rt.request_tick_detail_last("MASKED_TEST_ACCOUNT", 207, "JNU2612", 20)
    assert accepted is True
    assert len(rt._api.calls) == 1
    args = rt._api.calls[0]
    assert args[1] == ("enum", 207)
    assert args[2] == "JNU2612"
    assert args[3] == ("enum", 1)  # official LAST_COUNT
    assert args[4:7] == ("00:00:00", "23:59:59", 20)
    assert args[7] == "UTF8"


@pytest.mark.parametrize("bad", [0, 21, 1000])
def test_spark_runtime_tick_detail_count_cap(bad):
    rt = _runtime_for_query()
    with pytest.raises(ValueError):
        rt.request_tick_detail_last("MASKED_TEST_ACCOUNT", 207, "JNU2612", bad)
    assert rt._api.calls == []


def test_spark_runtime_tick_detail_response_has_separate_typed_hook():
    rt = object.__new__(SparkRuntime)
    rt._callbacks = deque(maxlen=10)
    rt._system_messages = deque(maxlen=10)
    rt._login_event = threading.Event()
    rt._system_event = threading.Event()
    got = []
    quote = []
    rt.on_tick_detail_callback = lambda mark, obj: got.append((mark, obj))
    rt.on_quote_callback = lambda *args: quote.append(args)
    payload = object()
    rt._on_response(1, 0, "GetStkTickDetail", None, payload)
    assert got == [(1, payload)]
    assert quote == []


def test_spark_runtime_invalid_symbol_does_not_call_api():
    rt = _runtime_for_query()
    with pytest.raises(ValueError):
        rt.request_tick_detail_last("MASKED_TEST_ACCOUNT", 207, "JNU\n2612", 20)
    assert rt._api.calls == []


def test_spark_runtime_correlates_request_time_separately_from_callback_time():
    rt = _runtime_for_query()
    rt._callbacks = deque(maxlen=10)
    rt._system_messages = deque(maxlen=10)
    rt._login_event = threading.Event()
    rt._system_event = threading.Event()
    rt.on_tick_detail_callback = None
    rt.on_quote_callback = None
    times = iter([
        datetime(2026, 9, 24, 6, 44, 59, tzinfo=UTC),
        datetime(2026, 9, 24, 6, 45, 1, tzinfo=UTC),
    ])
    rt._clock = lambda: next(times)

    assert rt.request_tick_detail_last("MASKED_TEST_ACCOUNT", 207, "JNU2612", 20) is True
    rt._on_response(1, 0, "GetStkTickDetail", None, _Result(market=207, stock="JNU2612"))

    pair = rt.latest_tick_detail_exchange()
    assert pair is not None
    request, callback = pair
    assert request.request_time_utc == datetime(2026, 9, 24, 6, 44, 59, tzinfo=UTC)
    assert callback.callback_received_at_utc == datetime(2026, 9, 24, 6, 45, 1, tzinfo=UTC)
    assert request.market_no == callback.returned_market_no == 207
    assert request.stock_code == callback.returned_stock_code == "JNU2612"
    assert request.accepted is True
    traces = rt.tick_detail_runtime_traces()
    assert "MASKED_TEST_ACCOUNT" not in repr(traces)


def test_spark_runtime_does_not_guess_between_ambiguous_tick_detail_requests():
    rt = _runtime_for_query()
    rt._callbacks = deque(maxlen=10)
    rt._system_messages = deque(maxlen=10)
    rt._login_event = threading.Event()
    rt._system_event = threading.Event()
    rt.on_tick_detail_callback = None
    rt.on_quote_callback = None
    times = iter([
        datetime(2026, 9, 24, 6, 45, 10, tzinfo=UTC),
        datetime(2026, 9, 24, 6, 45, 20, tzinfo=UTC),
        datetime(2026, 9, 24, 6, 45, 30, tzinfo=UTC),
    ])
    rt._clock = lambda: next(times)

    assert rt.request_tick_detail_last("MASKED_TEST_ACCOUNT", 207, "JNU2612", 20) is True
    assert rt.request_tick_detail_last("MASKED_TEST_ACCOUNT", 207, "JNU2612", 20) is True
    rt._on_response(1, 0, "GetStkTickDetail", None, _Result(market=207, stock="JNU2612"))

    traces = rt.tick_detail_runtime_traces()
    assert traces["callbacks"][-1]["request_id"] == ""
    assert rt.latest_tick_detail_exchange() is None
