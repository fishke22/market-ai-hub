"""Microstructure night-window features (pre-registered, extraction only).

Protocol: `research/phase3/MICROSTRUCTURE_NIGHT_WINDOW_PREREGISTRATION_v1.yaml`
(`AV2.MICROSTRUCTURE.NIGHT_WINDOW.v1`).

This module computes features and nothing else. It does not fit a model, does not produce a
probability, and does not create a holdout or an evidence channel. The recorded tick sample is
DEVELOPMENT_ONLY and can never be reported as out-of-sample evidence.

Enforced, not merely documented:
- `received_at` is the only ordering and cutoff clock (stored as VARCHAR ISO-8601 +00:00, so
  lexicographic comparison is chronological).
- Window = `received_at in [08:00Z, 21:00Z)` on trading date D = the OSE night session
  (17:00 JST D .. 06:00 JST D+1) expressed in the receipt clock. One instrument only.
- Trade source = the SPARK trade tape (`SubscribeStockTick` / `TRADE_TICK`), which carries
  `DealPrice`, `DealVol`, `BuyPrice`, `SellPrice`, `InOutFlag`. The `deal`/`vol` fields on
  `SubscribeWatchlistAll` are a last-trade snapshot, not the tape, and are not used here.
- `InOutFlag`: 0 and 1 were VERIFIED against the quote at trade time on recorded data
  (0 = at/below bid = seller-initiated; 1 = at/above ask = buyer-initiated). This is a
  measured convention, not an assumption; re-verify if the vendor changes the field.
- Non-finite and vendor-sentinel values are dropped before any arithmetic (never imputed).
- The frozen feature list is closed; adding one requires a protocol version bump.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from typing import Any

V2_MICROSTRUCTURE_SCHEMA_VERSION = "MS.1"
PROTOCOL_ID = "AV2.MICROSTRUCTURE.NIGHT_WINDOW.v1"

# Mirrors the recorder's vendor-sentinel contract: a "no value" is an absurd magnitude.
MAX_ABS_QUOTE_VALUE = 1e30

WINDOW_OPEN_UTC = time(8, 0)    # 17:00 JST
WINDOW_CLOSE_UTC = time(21, 0)  # 06:00 JST next day
MINIMUM_USABLE_TRADE_ROWS = 200
MINIMUM_WINDOW_MINUTES = 20.0

STATUS_OK = "OK"
STATUS_INSUFFICIENT_WINDOW = "INSUFFICIENT_WINDOW"
STATUS_NO_TRADE_ROWS = "NO_TRADE_ROWS"
STATUS_UNREADABLE = "STORE_UNREADABLE"
STATUS_SCHEMA_MISSING = "TAPE_FIELDS_NOT_IN_STORE"

FEATURE_NAMES: tuple[str, ...] = (
    "trade_count",
    "trade_volume",
    "window_minutes",
    "trades_per_minute",
    "window_log_return",
    "realized_vol",
    "vwap_deviation",
    "signed_volume_imbalance",
    "max_runup",
    "max_drawdown",
    "mean_trade_size",
    "quoted_spread_mean",
)

TAPE_CALLBACK = "SubscribeStockTick"
TAPE_KIND = "TRADE_TICK"


class MicrostructureError(Exception):
    """Base for protocol violations."""


class LeakageError(MicrostructureError):
    """A rule from the pre-registration was violated."""


def feature_names() -> tuple[str, ...]:
    return FEATURE_NAMES


def window_bounds(trading_date: str) -> tuple[datetime, datetime]:
    """Receipt-clock UTC bounds of the OSE night window for trading date D."""
    d = date.fromisoformat(str(trading_date))
    return (datetime.combine(d, WINDOW_OPEN_UTC, tzinfo=timezone.utc),
            datetime.combine(d, WINDOW_CLOSE_UTC, tzinfo=timezone.utc))


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out) or abs(out) >= MAX_ABS_QUOTE_VALUE:
        return None
    return out


@dataclass(frozen=True)
class WindowFeatures:
    trading_date: str
    instrument_code: str
    status: str
    reason: str = ""
    trade_count: int = 0
    window_start: datetime | None = None
    window_end: datetime | None = None
    features: dict[str, float | None] = field(default_factory=dict)
    schema_version: str = V2_MICROSTRUCTURE_SCHEMA_VERSION
    protocol_id: str = PROTOCOL_ID
    window_id: str = ""       # derived
    validation_status: str = "HYPOTHESIS_ONLY"
    is_probability: bool = False
    development_only: bool = True

    def __post_init__(self) -> None:
        unknown = sorted(set(self.features) - set(FEATURE_NAMES))
        if unknown:
            raise MicrostructureError(f"feature list is closed; unknown: {unknown}")

    def model_dump(self) -> dict:
        return asdict(self)

    def identity_payload(self) -> dict:
        d = asdict(self)
        d.pop("window_id", None)
        return d


def _identity(payload: dict) -> str:
    import json
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "v2ms_" + sha256(blob.encode("utf-8")).hexdigest()[:16]


def list_trading_dates(store_root) -> list[str]:
    from pathlib import Path

    root = Path(store_root)
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def _load_tape_rows(store_root, trading_date: str, instrument_code: str) -> list[tuple]:
    """Tape rows inside the receipt window, ordered by (received_at, _wal_seq)."""
    import duckdb
    from pathlib import Path

    start, end = window_bounds(trading_date)
    root = Path(store_root)
    day_dirs = [root / trading_date]
    for delta in (-1, 1):
        n = date.fromisoformat(str(trading_date)) + timedelta(days=delta)
        day_dirs.append(root / n.isoformat())
    present = [d for d in day_dirs if d.exists()]
    if not present:
        raise MicrostructureError("STORE_UNREADABLE: no partition for the requested date")

    sources = [f"read_parquet('{d.as_posix()}/*.parquet', union_by_name=true)" for d in present]
    src = sources[0] if len(sources) == 1 else (
        "(" + " UNION ALL BY NAME ".join(f"SELECT * FROM {s}" for s in sources) + ")")

    con = duckdb.connect()
    con.execute("SET enable_progress_bar=false")
    cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()}
    if not {"DealPrice", "DealVol"}.issubset(cols):
        raise MicrostructureError(
            f"{STATUS_SCHEMA_MISSING}: {sorted({'DealPrice', 'DealVol'} - cols)}")

    side = "InOutFlag" if "InOutFlag" in cols else "NULL AS InOutFlag"
    bid = "BuyPrice" if "BuyPrice" in cols else "NULL AS BuyPrice"
    ask = "SellPrice" if "SellPrice" in cols else "NULL AS SellPrice"
    seq = "_wal_seq" if "_wal_seq" in cols else "NULL AS _wal_seq"
    q = f"""
        SELECT received_at, DealPrice, DealVol, {side}, {bid}, {ask}, {seq}
        FROM {src}
        WHERE market_no = 207
          AND instrument_code = ?
          AND callback_type = ?
          AND microstructure_kind = ?
          AND received_at >= ? AND received_at < ?
        ORDER BY received_at, _wal_seq
    """
    try:
        return con.execute(q, [instrument_code, TAPE_CALLBACK, TAPE_KIND,
                               start.isoformat(), end.isoformat()]).fetchall()
    except Exception as exc:
        raise MicrostructureError(f"STORE_UNREADABLE: {type(exc).__name__}") from exc


def _compute_features(rows: list[tuple]) -> tuple[dict[str, float | None], int]:
    """Tape rows -> frozen feature vector. Values that cannot be computed stay None."""
    prices: list[float] = []
    sizes: list[float] = []
    times: list[datetime] = []
    buy_vol = 0.0
    sell_vol = 0.0
    spreads: list[float] = []
    for received_at, price, size, flag, bid, ask, _seq in rows:
        p = _finite(price)
        v = _finite(size)
        if p is None or p <= 0 or v is None or v <= 0:
            continue
        prices.append(p)
        sizes.append(v)
        times.append(received_at if isinstance(received_at, datetime)
                     else datetime.fromisoformat(str(received_at)))
        f = _finite(flag)
        if f == 1.0:
            buy_vol += v
        elif f == 0.0:
            sell_vol += v
        b, a = _finite(bid), _finite(ask)
        if b is not None and a is not None and a > b > 0:
            spreads.append(a - b)

    n = len(prices)
    out: dict[str, float | None] = {k: None for k in FEATURE_NAMES}
    if n == 0:
        return out, 0

    first, last = prices[0], prices[-1]
    out["trade_count"] = float(n)
    out["trade_volume"] = float(sum(sizes))
    out["mean_trade_size"] = float(sum(sizes) / n)

    minutes = (times[-1] - times[0]).total_seconds() / 60.0 if n >= 2 else 0.0
    out["window_minutes"] = float(minutes)
    if minutes > 0:
        out["trades_per_minute"] = float(n / minutes)

    if first > 0 and last > 0:
        out["window_log_return"] = float(math.log(last / first))

    if n >= 3:
        returns = [math.log(prices[i] / prices[i - 1]) for i in range(1, n) if prices[i - 1] > 0]
        if len(returns) >= 2:
            out["realized_vol"] = float(statistics.pstdev(returns))

    total_size = sum(sizes)
    if total_size > 0:
        vwap = sum(p * v for p, v in zip(prices, sizes)) / total_size
        if vwap > 0:
            out["vwap_deviation"] = float(math.log(last / vwap))

    signed = buy_vol + sell_vol
    if signed > 0:
        out["signed_volume_imbalance"] = float((buy_vol - sell_vol) / signed)

    if first > 0:
        ratios = [math.log(p / first) for p in prices if p > 0]
        if ratios:
            out["max_runup"] = float(max(ratios))
            out["max_drawdown"] = float(min(ratios))

    if spreads:
        out["quoted_spread_mean"] = float(sum(spreads) / len(spreads))
    return out, n


def extract_night_window(store_root, trading_date: str, instrument_code: str) -> WindowFeatures:
    """Deterministic, leakage-gated extraction for one instrument on one night window."""
    start, end = window_bounds(trading_date)
    try:
        rows = _load_tape_rows(store_root, trading_date, instrument_code)
    except MicrostructureError as exc:
        text = str(exc)
        status = STATUS_SCHEMA_MISSING if STATUS_SCHEMA_MISSING in text else STATUS_UNREADABLE
        return WindowFeatures(trading_date=trading_date, instrument_code=instrument_code,
                              status=status, reason=text,
                              window_start=start, window_end=end)

    features, n = _compute_features(rows)
    status, reason = STATUS_OK, ""
    if n == 0:
        status, reason = STATUS_NO_TRADE_ROWS, "no usable tape rows inside the receipt window"
    elif n < MINIMUM_USABLE_TRADE_ROWS:
        status = STATUS_INSUFFICIENT_WINDOW
        reason = f"tape rows {n} < {MINIMUM_USABLE_TRADE_ROWS}"
    elif (features.get("window_minutes") or 0.0) < MINIMUM_WINDOW_MINUTES:
        status = STATUS_INSUFFICIENT_WINDOW
        reason = f"window {features.get('window_minutes'):.1f} min < {MINIMUM_WINDOW_MINUTES}"

    window = WindowFeatures(
        trading_date=trading_date, instrument_code=instrument_code, status=status, reason=reason,
        trade_count=n, window_start=start, window_end=end,
        features={k: features[k] for k in FEATURE_NAMES} if status == STATUS_OK else {},
    )
    return WindowFeatures(**{**window.model_dump(), "window_id": _identity(window.identity_payload())})


def assert_target_after_cutoff(window: WindowFeatures, settlement_published_at: datetime,
                               *, information_cutoff: datetime | None = None) -> None:
    """TARGET_AFTER_CUTOFF: a target already known at the cutoff is leakage."""
    if window.status != STATUS_OK:
        raise MicrostructureError(f"window not usable: {window.status}")
    cutoff = information_cutoff or window.window_end
    if cutoff is None:
        raise MicrostructureError("window has no cutoff")
    for name, value in (("settlement_published_at", settlement_published_at),
                        ("information_cutoff", cutoff)):
        if value.tzinfo is None or value.utcoffset() is None:
            raise MicrostructureError(f"{name} must be timezone-aware")
    if settlement_published_at <= cutoff:
        raise LeakageError(
            "TARGET_AFTER_CUTOFF: settlement published at "
            f"{settlement_published_at.isoformat()} is not strictly after cutoff "
            f"{cutoff.isoformat()}")
