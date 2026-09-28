"""Isolated NautilusTrader 1.x P7 deterministic backtest runner.

This file is executed only by the isolated Nautilus Python. It must not import
MARKET_AI_HUB, access brokers, credentials, recorders, or network market data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import nautilus_trader
import pandas as pd
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import LoggingConfig, RiskEngineConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.trading.strategy import Strategy


class ParityStrategy(Strategy):
    def __init__(self, instrument_id, bar_type, bar_count: int):
        super().__init__()
        self.instrument_id = instrument_id
        self.bar_type = bar_type
        self.bar_count_target = int(bar_count)
        self.bars_seen = 0

    def on_start(self) -> None:
        self.subscribe_bars(self.bar_type)

    def on_bar(self, bar: Bar) -> None:
        self.bars_seen += 1
        if self.bars_seen == 2:
            order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.BUY,
                quantity=Quantity.from_int(1),
            )
            self.submit_order(order)
        elif self.bars_seen == self.bar_count_target - 2:
            self.close_all_positions(self.instrument_id)


def _bars(instrument, bar_count: int, seed: int, starting_price: float) -> tuple[BarType, list[Bar]]:
    bar_type = BarType.from_str(f"{instrument.id}-1-DAY-LAST-EXTERNAL")
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = float(starting_price)
    rows: list[Bar] = []
    for i in range(int(bar_count)):
        ticks = ((int(seed) + i * 17) % 7) - 3
        price = max(1.0, price + ticks * 0.25)
        ts = int((t0 + timedelta(days=i)).timestamp() * 1_000_000_000)
        rows.append(
            Bar(
                bar_type,
                Price.from_str(f"{price:.2f}"),
                Price.from_str(f"{price + 0.25:.2f}"),
                Price.from_str(f"{price - 0.25:.2f}"),
                Price.from_str(f"{price:.2f}"),
                Quantity.from_int(100),
                ts,
                ts,
            )
        )
    return bar_type, rows


def run(spec: dict) -> dict:
    expected_version = str(spec["engine_version"])
    if nautilus_trader.__version__ != expected_version:
        raise RuntimeError(
            f"ENGINE_VERSION_MISMATCH:{nautilus_trader.__version__}!={expected_version}"
        )
    bar_count = int(spec["bar_count"])
    seed = int(spec["seed"])
    starting_price = float(spec["starting_price"])
    if bar_count < 32:
        raise ValueError("bar_count must be >= 32")

    engine = BacktestEngine(
        BacktestEngineConfig(
            logging=LoggingConfig(log_level="ERROR"),
            risk_engine=RiskEngineConfig(bypass=True),
        )
    )
    try:
        instrument = TestInstrumentProvider.es_future(2026, 12)
        venue = Venue("GLBX")
        engine.add_venue(
            venue=venue,
            oms_type=OmsType.NETTING,
            account_type=AccountType.MARGIN,
            starting_balances=[Money(1_000_000, USD)],
            base_currency=USD,
            default_leverage=Decimal(10),
        )
        engine.add_instrument(instrument)
        bar_type, bars = _bars(instrument, bar_count, seed, starting_price)
        engine.add_data(bars)
        strategy = ParityStrategy(instrument.id, bar_type, bar_count)
        engine.add_strategy(strategy)
        engine.run()

        fills_df = engine.trader.generate_order_fills_report()
        account_df = engine.trader.generate_account_report(venue)
        fills = []
        for row in fills_df.to_dict(orient="records"):
            fills.append({
                "side": str(row.get("side")),
                "quantity": str(row.get("quantity")),
                "filled_qty": str(row.get("filled_qty")),
                "avg_px": float(row.get("avg_px")),
                "status": str(row.get("status")),
                "ts_init": int(pd.Timestamp(row.get("ts_init")).value),
                "ts_last": int(pd.Timestamp(row.get("ts_last")).value),
            })
        account_last = account_df.iloc[-1].to_dict() if not account_df.empty else {}
        result = {
            "schema_version": "AV2P7.NAUTILUS.RESULT.1",
            "engine": "nautilus_trader",
            "engine_version": nautilus_trader.__version__,
            "instrument_id": str(instrument.id),
            "input_bar_count": bar_count,
            "bars_seen": int(strategy.bars_seen),
            "orders_total": int(engine.cache.orders_total_count()),
            "positions_open": int(engine.cache.positions_open_count()),
            "positions_closed": int(engine.cache.positions_closed_count()),
            "fills": fills,
            "fill_count": len(fills),
            "account": {
                "total": str(account_last.get("total", "")),
                "free": str(account_last.get("free", "")),
                "currency": str(account_last.get("currency", "")),
            },
            "no_network_market_data": True,
            "no_live_adapter": True,
            "no_external_order_action": True,
        }
        digest_payload = json.dumps(result, sort_keys=True, separators=(",", ":"))
        result["result_digest"] = hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()
        return result
    finally:
        engine.dispose()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    spec = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = run(spec)
    Path(args.output).write_text(
        json.dumps(result, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
