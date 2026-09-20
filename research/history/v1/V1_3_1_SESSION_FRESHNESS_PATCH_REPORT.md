# V1_3_1_SESSION_FRESHNESS_PATCH_REPORT.md

日期：2026-09-19
範圍：`D:\MARKET_AI_HUB`（V1.3.1 SESSION/FRESHNESS SEMANTIC PATCH）
Gate：**READY_FOR_V1_FREEZE**

本輪只修一件事：把「市場是否正在交易」與「我們手上的資料是否新鮮」徹底分離。
未新增功能 / 模型 / Yuanta / 策略 / 重構。

---

## Root cause

V1.3 的 `quote_freshness` 把 staleness 直接寫進 session 欄位：
```
if freshness == "stale": market_open=False, tradable_now=False, session_status="stale"
```
這把兩個正交維度混在一起：資料舊 ≠ 市場休市。例如週二台股開盤中、但手上日線資料是三天前的 →
錯誤地被標成 market_open=false，且 session_status 出現非法的 "stale"。

## 修正後的欄位語義

| 欄位 | 由什麼決定 |
|------|-----------|
| `market_open` | 只由 exchange calendar / session rules |
| `tradable_now` | 只由商品交易制度與目前 session |
| `session_status` | `OPEN` / `CLOSED` / `PREOPEN` / `AFTER_HOURS` / `HOLIDAY_SESSION` / `UNKNOWN`（**不得用 STALE**） |
| `freshness_status` | `LIVE` / `RECENT` / `STALE` / `HISTORICAL` / `UNKNOWN`（只由 quote age / SLA） |
| `quote_live` | boolean，依 quote age / source SLA |
| `usable_for_live_decision` | boolean，只有資料夠新（quote_live）且完整才 true |

stale quote 只會造成 `quote_live=false`、`usable_for_live_decision=false`，
**不再**把 `market_open` / `tradable_now` 改成 false，也不再污染 `session_status`。

`services/market_session.py` 改為兩個獨立函式：
- `session_status()` → market_open / tradable_now / session_status（session 規則）
- `freshness_level(age, asset_class)` → LIVE/RECENT/STALE/HISTORICAL/UNKNOWN（純 age）
- `quote_freshness()` 合併兩者，但不互相覆寫。

`ForecastOutput` 新增 `quote_live` / `usable_for_live_decision`；Chronos/TimesFM forecast 皆注入。

## Regression tests（全過）

- **A** 週二 10:00 Taipei TWSE open + stale quote → market_open=true、tradable_now=true、
  freshness=STALE、quote_live=false、usable=false、session_status=OPEN
- **B** 週六 USDJPY → market_open=false、tradable_now=false、session=CLOSED；freshness 依實際 quote 判定
- **C** 週六 BTC → market_open=true、tradable_now=true、session=OPEN（24/7）
- **D** 閉市 + 新鮮最後 quote → market_open=false，但 freshness 不被強制 STALE
- `test_stale_does_not_flip_market_open`：週一 fx open，quote 很舊 → market_open 仍 true，
  只有 quote_live=false / usable=false
- session_status 語彙測：任何 symbol/時間都不會回 "STALE"

## Backward compatibility

- 既有欄位（market_open / tradable_now / freshness_status / session_status / source_timestamp /
  received_at / quote_age_seconds）全部保留；僅 session_status / freshness_status 的**列舉值**
  依本 prompt 明確要求改用大寫標準詞（"market_closed"→"CLOSED"、"open_24_7"→"OPEN"、"fresh"→"LIVE"、
  "stale"→"STALE"）。`tests/test_market_session.py` 已同步更新（此為本 prompt 指定的語彙變更）。

## 驗證

```
python -m pytest tests -q        → 154 passed
python tests/smoke_mcp.py        → MCP SMOKE: PASS（13 tools）
build_id                          → 4742a33e5b17d1d0
```

Live MCP（predict_chronos ^N225，週六 2026-09-19）：
`session_status=CLOSED`（非 STALE）、`freshness_status=STALE`、`quote_live=false`、
`usable_for_live_decision=false`、`market_open=false`（因 CLOSED 而非 stale）→ 語義正確分離。

## Unresolved issues（誠實列出）

1. FX session 仍為簡化模型（週六/週日全天休市，未含週五 22:00Z / 週日 22:00Z 精確邊界）。
2. TWSE/TSE 無 intraday 小時資料 → 交易日只標 OPEN（未細分 PREOPEN/AFTER_HOURS）。
3. `usable_for_live_decision` 的「完整」目前以 `complete` 參數近似（預設 true），
   尚未接上 OHLC 欄位完整性檢查。

## Gate

**READY_FOR_V1_FREEZE**

（使用者唯一動作：Cherry Studio 重啟 market-ai MCP，以 `health_check.build.build_id == 4742a33e5b17d1d0` 驗證。）
