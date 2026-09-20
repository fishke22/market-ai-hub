# Phase 2G.2 — Official Data Live Activation + Data Coverage Closure

- Gate: **PHASE2G2_PASS**
- build_id: `bbf3cb2f9a80d20e`（未變，V1 相容）
- 測試：**306 passed + 4 live**（154 V1 + 12 2A + 12 2B + 17 2C + 16 2D + 15 2D.1 + 14 2E + 18 2F + 21 2G + 11 2G.1 + 16 2G.2 unit + 4 2G.2 live）

## 核心結果：JPX Micro 真實資料已成功抓取

官方來源實測（非 PDF，是 xlsx/csv）：
| 來源 | 檔案 | Micro 實證（2026-09-18） |
|---|---|---|
| Settlement CSV | `rb20260918.csv`（SHIFT-JIS） | `FUT_225MC` 4 契約月：202610→64995、202611→65020、202612→65100、202703→65310 |
| Daily market data | `..._derivatives_market_data_whole_day.xlsx` | Micro 合計成交量 753,790 |
| Open Interest | `20260918open_interest.xlsx` | Micro 44 契約月列（202612 OI 54688） |

已保存：`data/raw/jpx/settlement/OSE/all/2026/09/rb20260918.parquet` + `data/strategy/micro_20260918_sample.json`。

## Provider 狀態（每個 provider：LIVE VERIFIED / CONTRACT ONLY / NEEDS CONFIG）

| Provider | 狀態 | 資料 | point-in-time | revision risk |
|---|---|---|---|---|
| JPX settlement（Micro/mini/Large） | **LIVE VERIFIED** | 清算價 per contract | 次營業日發布 → safe | 無（日快照） |
| JPX whole_day（成交量） | **LIVE VERIFIED** | per-product volume/value | safe | 無 |
| JPX open_interest | **LIVE VERIFIED** | per-contract OI | safe | 無 |
| JPX OHLC（open/high/low per contract） | CONTRACT ONLY | 現行 xlsx/csv 無 OHLC（settlement=close proxy） | — | — |
| JPX investor flow | CONTRACT ONLY | 未發現直接 CSV URL | — | — |
| BLS Public API v2 | **LIVE VERIFIED** | CPI/Core/Employment/Unemp/AHE | release 後才可用 | **有（BLS 修訂）** |
| BEA API | NEEDS CONFIG | GDP/PCE/Core PCE | — | 有 |
| Federal Reserve（FOMC calendar） | CONTRACT ONLY | HTML calendar（JSON URL 404） | — | — |
| BOJ | **LIVE VERIFIED** | release/MPM（HTML 可達） | — | — |
| Japan e-Stat | NEEDS CONFIG | CPI/employment（需 appId） | — | — |
| Japan Cabinet Office | CONTRACT ONLY | GDP release calendar | — | — |
| Japan MOF | CONTRACT ONLY | FX intervention（HTML） | — | — |
| EIA | NEEDS CONFIG | WTI/inventories（需 key） | — | — |
| SEC EDGAR | **LIVE VERIFIED** | filing timestamps（data.sec.gov 無 key） | safe | 無 |
| EDINET | NEEDS CONFIG | Japan filings | — | — |
| Cboe VIX | **LIVE VERIFIED** | VIX official daily history（CSV） | safe | 無 |

**Cboe = VIX authoritative historical source；Yahoo 退為 fallback。**

## Release-time correctness（`targets/release_time.py`）
- 區分 `observation_period / scheduled_release_time / actual_release_time / available_at`。
- 8 月 CPI 不得因 period=August 就在 8 月可見；release 後才可用（test 鎖定）。
- revision policy：FIRST_RELEASE / LATEST_REVISED；無歷史 vintage → `REVISION_RISK`，不假稱 point-in-time perfect。

## Data Coverage Auditor 升級（`targets/coverage.py`）
- 新 status：`LIVE_VERIFIED / HISTORICAL_VERIFIED / CONTRACT_ONLY / NEEDS_CONFIG / DELAYED / PROXY / MISSING`。
- `LiveCoverageAuditor.audit_osaka()`：28 個大阪 factor 逐項 source / coverage / freshness / status，真實反映缺口。

## Smart cache / Data Lake
- 整合 Phase 2E Data Lake（raw source + normalized + manifest + source hash）。
- 增量：只補 missing range（`missing_ranges`）；內容 hash 不變不重寫（`dedupe_and_write`）。

## No extra MCP sprawl
- 不為 BLS/BEA/Fed/BOJ/JPX/MOF/SEC/EIA 各裝 MCP；全作 MARKET_AI_HUB backend provider。
- TradingView MCP 保持 OPTIONAL。

## Tests
- unit（16）：settlement csv / settlement-not-close / micro listing date / whole_day xlsx / open_interest xlsx /
  investor flow / BLS mock / Fed calendar / BOJ / MOF / Cboe VIX / release-time no-lookahead / revision-risk /
  incremental / cache reuse / coverage live status。
- live smoke（4，`-m live`）：JPX Micro（settlement+whole_day）、BLS、Cboe VIX、SEC EDGAR → **全 PASS**。
- 網路 provider tests 分 unit（mocked）與 live（`@pytest.mark.live`，預設排除），避免外站暫失效導致全 fail。

## Gate 條件核對
1. ✅ JPX Micro 真實資料成功抓取（settlement 4 契約月 + volume + OI，LIVE VERIFIED）
2. ✅ 核心 Macro 官方來源 live 驗證（BLS / Cboe / SEC EDGAR / BOJ）
3. ✅ release-time leakage tests PASS
4. ✅ Data Coverage Auditor 真實反映缺口
5. ✅ 全 regression PASS（306 passed）

## Blockers
- 無。
- 誠實揭露：
  - JPX per-contract **OHLC**（open/high/low）不在官方 xlsx/csv，僅 settlement 作 close proxy（CONTRACT_ONLY）。
  - **Full Micro historical backfill 尚未 bulk 執行**（僅驗證單日，避免大量抓取）；URL pattern 已確認，待後續排程。
  - JPX investor flow 未發現直接 CSV URL（CONTRACT ONLY）。
  - Fed FOMC JSON 404，calendar 走 HTML（CONTRACT ONLY）。

## 驗證
- `pytest tests/ -q` → 306 passed（4 live deselected）
- `pytest tests/test_phase2g2.py -m live -q` → 4 passed（真實連線）
- `build_id` 維持 `bbf3cb2f9a80d20e`
