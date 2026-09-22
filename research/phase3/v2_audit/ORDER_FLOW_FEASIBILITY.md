# ORDER FLOW FEASIBILITY (V2)

Strict data-layer separation and a claim rule. Conclusion: **no true order-flow is available; OHLCV only.**

## Data layer separation

| Layer | Fields | Current status |
|---|---|---|
| OHLCV | open/high/low/close/volume | `AVAILABLE` (daily only) |
| L1 | bid, ask, bid size, ask size | `NOT_AVAILABLE` |
| L2 | depth book | `NOT_AVAILABLE` (NO_L2_FOUND) |
| Order-event | market buy/sell, trade size, cancellation | `NOT_AVAILABLE` |

## Field audit

| Field | Status |
|---|---|
| Bid | NOT_AVAILABLE |
| Ask | NOT_AVAILABLE |
| Bid Size | NOT_AVAILABLE |
| Ask Size | NOT_AVAILABLE |
| Market Buy / Sell (aggressor side) | NOT_AVAILABLE |
| Trade Size | NOT_AVAILABLE |
| Cancellation | NOT_AVAILABLE |
| Depth | NOT_AVAILABLE |

## Claim rule (enforced)

With OHLCV only, the system **must not** claim:
`true OFI, true cumulative delta, depth imbalance, cancellation pressure`.
Only "proxy" may be used (e.g. up-volume/down-volume proxy from OHLCV + close direction).

## Feature classification (future order-flow features)

Each order-flow feature must be tagged:
`AVAILABLE_NOW` / `L1_REQUIRED` / `L2_REQUIRED` / `ORDER_EVENT_REQUIRED` / `NOT_AVAILABLE`.

## Data latency contract (design)

`source_timestamp, observed_at, staleness_seconds, frequency, market_open_status, availability`,
optionally rolled up into a `Market Context Quality Score`.

## Feasibility conclusion

- Order-flow **impossible today** on current data (no L1/L2/order events).
- Only OHLCV-derived **proxies** are buildable.
- True order-flow is `DATA_DEPENDENT` and requires licensing (JPX/TAIFEX/OSE market data + L1/L2).
