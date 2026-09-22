# INTRADAY DATA FEASIBILITY (V2)

## Per-target intraday feasibility

| Target | 1m | 5m | 15m | 30m | 60m | Session Close | dynamic state update |
|---|---|---|---|---|---|---|---|
| OSAKA_MICRO | NO | NO | NO | NO | NO | daily only | NO (daily only) |
| TAIWAN_STOCK | NO | NO | NO | NO | NO | daily only | NO |
| TAIWAN_INDEX | NO | NO | NO | NO | NO | daily only | NO |

> Only **daily** data exists (OSE micro 960 daily bars; TWSE 916 daily snapshots). There is **no
> 1m/5m/15m/30m/60m** bar data for any target. Dynamic intraday state update is **not possible
> today**.

## What exists vs what is claimed

- Minute OHLCV: `NOT_AVAILABLE`.
- Tick: `NOT_AVAILABLE`.
- L1/L2/order events: `NOT_AVAILABLE`.
- The `TaifexProvider.fetch_time_and_sales` is a **daily historical CSV**, not a live order feed.

## Data acquisition gaps (design — no purchase/subscription performed)

| Need | Frequency | History | Timestamp quality | L1/L2 | Licensing | Source class | Storage est. | Runtime cost |
|---|---|---|---|---|---|---|---|---|
| OSE micro intraday | 1m/5m/tick | ≥2y | ms, tz-aware | optional | JPX/OSE market data license | market-data vendor / JPX | large (tick) | streaming + tick store |
| TW stock intraday | 1m/5m | ≥2y | s | optional | TWSE/FinMind premium | FinMind / broker | medium | polling |
| TAIEX intraday | 1m | ≥2y | s | no | TWSE | vendor | medium | polling |
| L1 | bid/ask+size | ≥1y | ms | yes | vendor | direct feed | high | streaming |
| L2 | depth | ≥1y | ms | yes | vendor | direct feed | very high | streaming |

## Conclusion

Intraday (1m/5m/…) and order-flow capabilities are **DATA_DEPENDENT** and require new licensed data.
The current system is **daily-only** and must not present itself as intraday-capable.
