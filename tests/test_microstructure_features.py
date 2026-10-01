"""Microstructure night-window feature protocol tests (extraction only, no model)."""
from __future__ import annotations

import math
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, "src")

from market_ai_hub.research.v2 import microstructure_features as MS

UTC = timezone.utc


def _store(tmp_path, date_str, rows, instrument="JNUPM2612"):
    """Write a minimal but真实-shaped parquet partition with the tape columns."""
    import duckdb

    part = tmp_path / "parquet" / date_str
    part.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("""CREATE TABLE t (
        provider VARCHAR, callback_type VARCHAR, market_no BIGINT, instrument_code VARCHAR,
        received_at VARCHAR, _wal_seq BIGINT, microstructure_kind VARCHAR,
        DealPrice DOUBLE, DealVol DOUBLE, InOutFlag DOUBLE, BuyPrice DOUBLE, SellPrice DOUBLE)""")
    for i, r in enumerate(rows):
        con.execute("INSERT INTO t VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
            "YUANTA_SPARK", "SubscribeStockTick", 207, instrument, r["received_at"], i,
            "TRADE_TICK", r["price"], r["size"], r.get("flag"), r.get("bid"), r.get("ask")])
    con.execute(f"COPY t TO '{(part / 'p.parquet').as_posix()}' (FORMAT PARQUET)")
    con.close()
    return tmp_path / "parquet"


def _tape(n=400, start_offset_min=0, step_s=30, price0=68000.0, drift=0.0):
    base = datetime(2026, 10, 1, 9, 0, tzinfo=UTC) + timedelta(minutes=start_offset_min)
    rows = []
    for i in range(n):
        p = price0 + drift * i
        rows.append({
            "received_at": (base + timedelta(seconds=step_s * i)).isoformat(),
            "price": p, "size": 2.0, "flag": 1.0 if i % 2 == 0 else 0.0,
            "bid": p - 5.0, "ask": p + 5.0,
        })
    return rows


# ── frozen contract ───────────────────────────────────────────────────────────
def test_protocol_id_and_frozen_feature_list():
    assert MS.PROTOCOL_ID == "AV2.MICROSTRUCTURE.NIGHT_WINDOW.v1"
    assert MS.feature_names() == (
        "trade_count", "trade_volume", "window_minutes", "trades_per_minute",
        "window_log_return", "realized_vol", "vwap_deviation", "signed_volume_imbalance",
        "max_runup", "max_drawdown", "mean_trade_size", "quoted_spread_mean")


def test_unknown_feature_is_rejected():
    with pytest.raises(MS.MicrostructureError):
        MS.WindowFeatures(trading_date="2026-10-01", instrument_code="X", status="OK",
                          features={"not_registered": 1.0})


def test_window_bounds_are_the_receipt_clock_night_session():
    start, end = MS.window_bounds("2026-10-01")
    assert (start, end) == (datetime(2026, 10, 1, 8, 0, tzinfo=UTC),
                            datetime(2026, 10, 1, 21, 0, tzinfo=UTC))
    assert (end - start) == timedelta(hours=13)   # 17:00 JST .. 06:00 JST


# ── leakage gates ─────────────────────────────────────────────────────────────
def test_target_must_be_published_strictly_after_cutoff(tmp_path):
    root = _store(tmp_path, "2026-10-01", _tape())
    w = MS.extract_night_window(root, "2026-10-01", "JNUPM2612")
    assert w.status == MS.STATUS_OK
    with pytest.raises(MS.LeakageError):
        MS.assert_target_after_cutoff(w, w.window_end - timedelta(minutes=1))
    MS.assert_target_after_cutoff(w, w.window_end + timedelta(seconds=1))


def test_naive_datetime_is_rejected_as_leakage_input(tmp_path):
    root = _store(tmp_path, "2026-10-01", _tape())
    w = MS.extract_night_window(root, "2026-10-01", "JNUPM2612")
    with pytest.raises(MS.MicrostructureError):
        MS.assert_target_after_cutoff(w, datetime(2026, 10, 2, 0, 0))


def test_unusable_window_cannot_be_used_as_evidence(tmp_path):
    root = _store(tmp_path, "2026-10-01", _tape(n=10))          # below the minimum
    w = MS.extract_night_window(root, "2026-10-01", "JNUPM2612")
    assert w.status == MS.STATUS_INSUFFICIENT_WINDOW
    assert w.features == {}
    with pytest.raises(MS.MicrostructureError):
        MS.assert_target_after_cutoff(w, datetime(2026, 10, 2, tzinfo=UTC))


# ── value sanitation ──────────────────────────────────────────────────────────
def test_nonfinite_and_sentinel_values_are_dropped_not_imputed():
    assert MS._finite(float("nan")) is None
    assert MS._finite(float("inf")) is None
    assert MS._finite(6.755378e38) is None
    rows = [
        ("2026-10-01T09:00:00+00:00", 68000.0, 2.0, 1.0, 67995.0, 68005.0, 1),
        ("2026-10-01T09:00:30+00:00", float("nan"), 2.0, 1.0, 67995.0, 68005.0, 2),
        ("2026-10-01T09:01:00+00:00", 6.755378e38, 2.0, 1.0, 67995.0, 68005.0, 3),
        ("2026-10-01T09:01:30+00:00", 68010.0, float("inf"), 1.0, 67995.0, 68005.0, 4),
        ("2026-10-01T09:02:00+00:00", 68020.0, 2.0, 0.0, 68000.0, 68010.0, 5),
    ]
    feats, n = MS._compute_features(rows)
    assert n == 2                                   # only two usable rows
    assert feats["trade_volume"] == 4.0
    assert feats["trade_count"] == 2.0


# ── feature maths (synthetic, exact) ──────────────────────────────────────────
def test_exact_feature_maths_on_synthetic_tape():
    rows = [
        ("2026-10-01T09:00:00+00:00", 100.0, 1.0, 1.0, 99.0, 101.0, 1),
        ("2026-10-01T09:01:00+00:00", 110.0, 3.0, 1.0, 109.0, 111.0, 2),
        ("2026-10-01T09:02:00+00:00", 90.0, 1.0, 0.0, 89.0, 91.0, 3),
    ]
    f, n = MS._compute_features(rows)
    assert n == 3
    assert f["trade_count"] == 3.0
    assert f["trade_volume"] == 5.0
    assert f["mean_trade_size"] == pytest.approx(5.0 / 3)
    assert f["window_minutes"] == pytest.approx(2.0)
    assert f["trades_per_minute"] == pytest.approx(1.5)
    assert f["window_log_return"] == pytest.approx(math.log(90.0 / 100.0))
    assert f["max_runup"] == pytest.approx(math.log(110.0 / 100.0))
    assert f["max_drawdown"] == pytest.approx(math.log(90.0 / 100.0))
    # VWAP = (100*1 + 110*3 + 90*1) / 5 = 520/5 = 104
    assert f["vwap_deviation"] == pytest.approx(math.log(90.0 / 104.0))
    # buy 1+3 = 4, sell 1 -> (4-1)/5
    assert f["signed_volume_imbalance"] == pytest.approx(0.6)
    assert f["quoted_spread_mean"] == pytest.approx(2.0)
    assert f["realized_vol"] is not None and f["realized_vol"] >= 0


def test_signed_imbalance_uses_the_verified_flag_mapping():
    rows = [("2026-10-01T09:00:00+00:00", 100.0, 5.0, 1.0, None, None, 1),
            ("2026-10-01T09:01:00+00:00", 100.0, 1.0, 0.0, None, None, 2)]
    f, _ = MS._compute_features(rows)
    assert f["signed_volume_imbalance"] == pytest.approx((5.0 - 1.0) / 6.0)
    rows2 = [("2026-10-01T09:00:00+00:00", 100.0, 5.0, None, None, None, 1),
             ("2026-10-01T09:01:00+00:00", 100.0, 1.0, None, None, None, 2)]
    f2, _ = MS._compute_features(rows2)
    assert f2["signed_volume_imbalance"] is None      # unknown side is never guessed


def test_spread_ignores_inverted_or_nonpositive_quotes():
    rows = [("2026-10-01T09:00:00+00:00", 100.0, 1.0, 1.0, 99.0, 101.0, 1),
            ("2026-10-01T09:01:00+00:00", 100.0, 1.0, 1.0, 105.0, 101.0, 2),  # inverted
            ("2026-10-01T09:02:00+00:00", 100.0, 1.0, 1.0, 0.0, 0.0, 3)]      # non-positive
    f, _ = MS._compute_features(rows)
    assert f["quoted_spread_mean"] == pytest.approx(2.0)


# ── end-to-end through a real partition ───────────────────────────────────────
def test_extraction_is_deterministic_and_content_addressed(tmp_path):
    root = _store(tmp_path, "2026-10-01", _tape())
    a = MS.extract_night_window(root, "2026-10-01", "JNUPM2612")
    b = MS.extract_night_window(root, "2026-10-01", "JNUPM2612")
    assert a.status == MS.STATUS_OK
    assert a.window_id and a.window_id == b.window_id
    assert a.model_dump() == b.model_dump()
    assert a.development_only is True
    assert a.validation_status == "HYPOTHESIS_ONLY"
    assert a.is_probability is False


def test_rows_outside_the_receipt_window_are_excluded(tmp_path):
    inside = _tape(n=400)
    # a trade at 22:00Z is past the 21:00Z close and must not contribute
    outside = [{"received_at": "2026-10-01T22:00:00+00:00", "price": 1.0, "size": 1.0,
                "flag": 1.0, "bid": 0.5, "ask": 1.5}]
    root = _store(tmp_path, "2026-10-01", inside + outside)
    w = MS.extract_night_window(root, "2026-10-01", "JNUPM2612")
    assert w.status == MS.STATUS_OK
    assert w.trade_count == len(inside)


def test_missing_tape_columns_are_reported_not_guessed(tmp_path):
    import duckdb

    part = tmp_path / "parquet" / "2026-10-01"
    part.mkdir(parents=True)
    con = duckdb.connect()
    con.execute("CREATE TABLE t (provider VARCHAR, callback_type VARCHAR, market_no BIGINT, "
                "instrument_code VARCHAR, received_at VARCHAR, _wal_seq BIGINT, deal DOUBLE)")
    con.execute("INSERT INTO t VALUES ('p','SubscribeWatchlistAll',207,'JNUPM2612',"
                "'2026-10-01T09:00:00+00:00',1,68000.0)")
    con.execute(f"COPY t TO '{(part / 'p.parquet').as_posix()}' (FORMAT PARQUET)")
    con.close()
    w = MS.extract_night_window(tmp_path / "parquet", "2026-10-01", "JNUPM2612")
    assert w.status == MS.STATUS_SCHEMA_MISSING
    assert w.features == {}


def test_snapshot_rows_are_never_mixed_into_the_tape(tmp_path):
    """A SubscribeWatchlistAll row with an extreme deal must not contribute to any feature."""
    import duckdb

    root = _store(tmp_path, "2026-10-01", _tape())
    part = root / "2026-10-01"
    con = duckdb.connect()
    con.execute("""CREATE TABLE snap (
        provider VARCHAR, callback_type VARCHAR, market_no BIGINT, instrument_code VARCHAR,
        received_at VARCHAR, _wal_seq BIGINT, microstructure_kind VARCHAR,
        DealPrice DOUBLE, DealVol DOUBLE, InOutFlag DOUBLE, BuyPrice DOUBLE, SellPrice DOUBLE)""")
    con.execute("INSERT INTO snap VALUES ('YUANTA_SPARK','SubscribeWatchlistAll',207,"
                "'JNUPM2612','2026-10-01T09:00:15+00:00',99,NULL,99999.0,1000.0,1.0,0.0,0.0)")
    con.execute(f"COPY snap TO '{(part / 'snapshot.parquet').as_posix()}' (FORMAT PARQUET)")
    con.close()

    w = MS.extract_night_window(root, "2026-10-01", "JNUPM2612")
    assert w.status == MS.STATUS_OK
    assert w.trade_count == len(_tape())
    assert w.features["max_runup"] < math.log(99999.0 / 68000.0)
