# DATA SOURCE AUDIT (V2)

Read-only audit of actual on-disk data + provider implementations. `NOT_AVAILABLE` = verified absent; `UNKNOWN` = not verifiable locally.

## On-disk data inventory (verified paths)

| Path | Content | Notes |
|---|---|---|
| `data/normalized/ose_micro/ose_micro_daily_bar_v1.parquet` | 960 rows, cols `trading_date,open,high,low,close,volume,count` | **DAILY** only |
| `data/normalized/ose_micro/preclose_snapshots.parquet` | 330 rows, `trading_date,close_T,open_T1,p60,p30,p15,p5` | daily pre-close percentiles |
| `data/raw/jpx/settlement/OSE/all/2026/09/rb20260918.parquet` | 39 rows, `contract,product,settlement_price,final_settlement_price,date,source_url,source_hash` | JPX settlement (current-day only) |
| `data/cache/twse/` (916 files) | TWSE daily OHLCV snapshot (Date/Code/Name/OHLC/TradeVolume/TradeValue/Transaction) | daily, ROC calendar dates |
| `data/cache/taifex/` (1 file) | TAIFEX daily cache | daily |
| `data/cache/ustreasury/` (1 file) | US Treasury par yield daily | daily |
| `data/feature_store/features.duckdb` | 547 rows, `close` for `^N225`, `RESEARCH_PROXY` | daily, 2025-09-17..2026-06-30 |
| `data/validation_samples/2026-09-21/fresh_validation_sample.json` | fresh sample | engineering validation only |

## Per-source audit

| Source | Provider impl | Freq | Status |
|---|---|---|---|
| OSE Nikkei 225 Micro | JPX settlement (`targets/jpx_settlement.py`) | daily (settlement) | direct; **no intraday/bar history** |
| ^N225 (proxy) | `providers/yfinance_provider.py`, `providers/jquants.py` | daily | proxy only |
| TAIEX / ^TWII | `providers/yfinance_provider.py` (.TW fallback), TWSE index | daily | forecast target only (non-executable) |
| Taiwan stocks | `providers/finmind.py` (adjusted), `providers/twse.py` (daily all) | daily | 916-day TWSE cache present |
| TX / MTX / TMF | `providers/taifex.py` | daily | execution instruments; cache minimal (1 file) |
| Nasdaq futures | **NOT_AVAILABLE** — no dedicated provider; only cross-market yfinance symbols | daily (via yfinance if requested) | UNKNOWN coverage |
| S&P futures | NOT_AVAILABLE (dedicated) | — | via yfinance only |
| SOX | NOT_AVAILABLE (dedicated) | — | leakage.py references `SOX_tomorrow` but no provider |
| USDJPY | NOT_AVAILABLE (dedicated) | — | via yfinance only |
| VIX | NOT_AVAILABLE (dedicated) | — | via yfinance only |
| US Treasury yields | `providers/ustreasury.py` | daily | 1 cached file |
| FRED macro | `providers/fred.py` (needs `FRED_API_KEY`) | daily/periodic | CONFIGURED (WinCred) |
| Brent / WTI | NOT_AVAILABLE (dedicated) | — | via yfinance only |
| TWSE | `providers/twse.py` | daily | implemented |
| FinMind | `providers/finmind.py` (needs `FINMIND_API_TOKEN`) | daily | CONFIGURED (WinCred) |
| TAIFEX | `providers/taifex.py` | daily | implemented |
| JPX | `providers/jquants.py` (J-Quants, needs config) | daily | delayed/free-plan |
| yfinance | `providers/yfinance_provider.py` | daily | implemented |
| Yuanta | `integrations/yuanta/*` | quote (read-only gate) | INTERFACE_ONLY |
| TradingView | `integrations/tradingview_bridge.py` | display | INTERFACE_ONLY |

## Raw data detail matrix (fields actually available)

| Dataset | OHLCV | Bid/Ask | Bid/Ask Size | Trade side/size | L1 | L2 | order events | cancellations | OI | settlement | volume | contract id | session id | license |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| OSE micro daily bar | OHLCV | NO | NO | NO | NO | NO | NO | NO | NO | NO (bar) | YES | NO | NO | local-only |
| OSE micro preclose | close/open + p5/p15/p30/p60 | NO | NO | NO | NO | NO | NO | NO | NO | NO | NO | NO | NO | local-only |
| JPX settlement | — | NO | NO | NO | NO | NO | NO | NO | NO | YES | NO | YES (contract) | NO | official |
| TWSE daily | OHLCV | NO | NO | NO | NO | NO | NO | NO | NO | NO | YES | YES (Code) | NO | official |
| TAIFEX daily | OHLCV(partial) | NO | NO | NO | NO | NO | NO | NO | NO | NO | partial | YES | NO | official |
| US Treasury | yields | — | — | — | — | — | — | — | — | — | — | — | — | official |

## Osaka Micro historical verification (explicit)

- **1-minute**: `NOT_AVAILABLE` (no 1m parquet/csv/duckdb found).
- **tick**: `NOT_AVAILABLE`.
- **volume**: `YES` (daily bar `volume` column).
- **OI (open interest)**: `NOT_AVAILABLE`.
- **bid/ask**: `NOT_AVAILABLE`.
- **L1/L2**: `NOT_AVAILABLE` (NO_L2_FOUND).
- **session coverage**: daily bars only; no day/night split field.
- **night session coverage**: `NOT_AVAILABLE`.
- **holiday trading coverage**: calendar config marks 2026-09-21/22/23; bar data does not separately tag holiday-trading sessions.
- **contract roll semantics**: `targets/continuous.py` + `services/cross_source.py`; center-month continuous only (225LABO), non-executable research series.
- **continuous series semantics**: 225LABO center-month continuous (`LOCAL_ONLY`, not contract/settlement).

> Conclusion: minute OHLCV **does not** imply order flow. No tick/L1/L2/bid-ask/OI exists for any target.

## Data frequency matrix

| Source | 1m | 5m | 15m | 30m | 60m | daily | tick | L1 | L2 |
|---|---|---|---|---|---|---|---|---|---|
| OSE micro | NO | NO | NO | NO | NO | YES | NO | NO | NO |
| ^N225 | NO | NO | NO | NO | NO | YES | NO | NO | NO |
| TAIEX | NO | NO | NO | NO | NO | YES | NO | NO | NO |
| Taiwan stocks | NO | NO | NO | NO | NO | YES | NO | NO | NO |
| TX/MTX/TMF | NO | NO | NO | NO | NO | YES | NO | NO | NO |
| US Treasury | — | — | — | — | — | YES | — | — | — |
| FRED | — | — | — | — | — | YES/periodic | — | — | — |
| yfinance (any) | UNKNOWN (interval param exists but not exercised) | — | — | — | — | YES | — | — | — |

## Secret / credential status (no values disclosed)

- `FRED_API_KEY`: CONFIGURED (WinCred `MARKET_AI_HUB/FRED_API_KEY`).
- `FINMIND_API_TOKEN`: CONFIGURED (WinCred `MARKET_AI_HUB/FINMIND_API_TOKEN`).
- Yuanta ID/password: NOT_CONFIGURED (or gate-only); no secret value disclosed.
- All other provider tokens: NOT_CONFIGURED.
