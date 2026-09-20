# PHASE 2V-D — FORWARD SHADOW SETUP REPORT

- Gate: **PHASE2VD_PASS**（infrastructure 正確建立並啟動；不代表 forward edge confirmed）
- 前置: PHASE2VA_PASS / PHASE2VB_PASS / PHASE2VB3_PASS / PHASE2VC_PASS / PHASE2VC1_PASS

---

## 0. 本棒範圍

只做 **REAL-TIME / FORWARD RESEARCH FORECAST SHADOW**。不是 paper trading / strategy validation / broker simulation。無 PnL / position / order。

## 1. 交付物

| 檔案 | 說明 |
|------|------|
| `FORWARD_SHADOW_PROTOCOL.yaml` | v1 frozen（scope/target/models/metrics/labels/activation 規則） |
| `FORWARD_SHADOW_ACTIVATION.yaml` | activated_at + build_id + cohort |
| `src/market_ai_hub/research/forward_shadow.py` | 核心（create_daily_forecasts / settle_pending / build_status / init_activation） |
| `scripts/run_forward_shadow.ps1` | 每日 research forecast + registry write |
| `scripts/settle_forward_predictions.ps1` | settle append-only |
| `FORWARD_SHADOW_STATUS.json` | 狀態（forecasts/pending/settled/metrics） |
| `FORWARD_SHADOW_REPORT.md` | 人讀報告（historical vs forward 分開） |
| `FORWARD_VALIDATION_MANIFEST.yaml` | manifest |
| `PHASE2VD_FORWARD_SHADOW_SETUP_REPORT.md` | 本檔 |

## 2. 驗證結果（smoke test）

- `init_activation` ✓（activated_at 2026-09-20, build_id ccabe1e1552d9ae7）
- `create_daily_forecasts` ✓（資料 stale 時正確回 FORECAST_SKIPPED_DATA_QUALITY）
- `settle_pending` ✓（robust 處理 NaT origin，append-only）
- `build_status` ✓（生成 FORWARD_SHADOW_STATUS.json）
- registry append-only / immutable 驗證 ✓（重複 forecast_id 拒絕）

## 3. 資料 freshness 現況

- 225LABO Micro bars 最後日期 2026-09-01（19 天 stale）
- freshness gate（7 天）正確跳過 stale 資料
- **forward evidence 需使用者更新資料 + 每日執行**，不能 backfill

## 4. 設計保證（對應 protocol）

| 保證 | 實作 |
|------|------|
| Append-only forecast | registry 拒絕重複 forecast_id |
| Append-only outcome | registry 拒絕重複 settle |
| No backfill as forward | activation timestamp 為邊界 |
| Model frozen | VAR(1) AR(1) lag=1，無每日調參 |
| Baseline same-origin | VAR + LAST_VALUE + ZERO_RETURN 同 origin |
| Data quality gate | stale → SKIP |
| No trading signal | MCP 只回 forecast/quality/state |
| No auto promotion | AUTO_PROMOTE=false |

## 5. Gate

**PHASE2VD_PASS**（infrastructure 建立並啟動正確）。

- 不是 forward edge confirmed（那需未來真實交易日累積）
- forward evidence 目前 = NONE_YET（資料 stale）
- 歷史結論維持：VAR = STATISTICAL FORECAST EVIDENCE 但 NON_EXECUTABLE_FORECAST_EDGE

## 6. 未做的事

- 未 GitHub publication / Live Trading / broker login / paper trading / strategy promotion
- 未自動啟用 Windows Task Scheduler（default disabled）
- 未 backfill historical forecasts
