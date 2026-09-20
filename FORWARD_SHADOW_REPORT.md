# FORWARD SHADOW REPORT

> 本報告明確區分 HISTORICAL EVIDENCE 與 FORWARD EVIDENCE，兩者不可混。

---

## HISTORICAL EVIDENCE（已完成的歷史 OOS 驗證）

| Phase | 結論 |
|-------|------|
| 2V-B (Proxy ^N225) | 全模型 NO_EVIDENCE |
| 2V-B.3 (Direct Micro) | VAR(1) = STATISTICAL FORECAST EVIDENCE（MASE=0.958, dir_acc=62.2%, MCC=0.241, 顯著） |
| 2V-C (可執行策略) | NO_ECONOMIC_EDGE（open-to-close 反向 -0.378, -259 pts/trade） |
| 2V-C.1 (因果性) | NON_EXECUTABLE_FORECAST_EDGE（edge 在 gap 85.2%，但需當日 full close，pre-close 崩潰 41.3%） |

**歷史結論**：VAR(1) 有真實統計 forecast edge，但本質上 non-causal / non-executable。無 strategy candidate，無 production candidate。

---

## FORWARD EVIDENCE（本棒啟用後累積）

### 狀態：NONE_YET

- **Activation**：2026-09-20（`FORWARD_SHADOW_ACTIVATION.yaml`）
- **Forward evidence = 0**（尚未累積任何真正 forward forecast）

### 為什麼是 0？

1. **資料 stale**：225LABO Micro bars 最後日期 2026-09-01（距今 19 天）。freshness gate（7 天）正確觸發 `FORECAST_SKIPPED_DATA_QUALITY`。
2. **不能 backfill**：歷史日期不得事後補成 forward（section 10 / 40）。
3. **真正 forward evidence 需要**：使用者更新 225LABO 資料（下載最新 bars）+ 每日執行 `scripts/run_forward_shadow.ps1`。

### 目前 registry 狀態

- forecasts_created: 17（8 筆來自 2V-A 歷史、9 筆為本棒 smoke test，皆 origin < activation，屬 REPLAY）
- pending: 17，settled: 0
- 這些 smoke-test forecasts 明確是 REPLAY（origin 2026-09-01 < activation 2026-09-20），**不計入 forward evidence**。

---

## 基礎設施（本棒交付）

| 元件 | 狀態 |
|------|------|
| `FORWARD_SHADOW_PROTOCOL.yaml` | ✓ v1 frozen |
| `FORWARD_SHADOW_ACTIVATION.yaml` | ✓ activated 2026-09-20 |
| `src/market_ai_hub/research/forward_shadow.py` | ✓ core（create/settle/status） |
| `scripts/run_forward_shadow.ps1` | ✓ research forecast + registry write |
| `scripts/settle_forward_predictions.ps1` | ✓ settle append-only |
| `FORWARD_SHADOW_STATUS.json` | ✓ 自動生成 |

### 設計保證

- **Append-only**：forecast 建立後不可改；outcome append-only。
- **無 backfill**：activation 前永遠不算 forward。
- **Model frozen**：VAR(1) AR(1) lag=1，不每日調參；改模型 → model_version+1 獨立 cohort。
- **Baseline same-origin**：VAR + LAST_VALUE + ZERO_RETURN 同 origin/target/horizon。
- **資料品質 gate**：stale → FORECAST_SKIPPED_DATA_QUALITY（比硬產生 forecast 好）。
- **無 trading**：MCP 不回 BUY/SELL；無 PnL/position/order；AUTO_PROMOTE=false。
- **Label**：RESEARCH_FORECAST_ONLY / NON_EXECUTABLE_FORECAST_EDGE。

---

## 下一步（當 fresh data 可用時）

1. 更新 225LABO 資料（下載最新 daily bars）。
2. 每日收盤後執行 `scripts/run_forward_shadow.ps1`（建立 VAR + baselines forecast）。
3. 次日資料到位後執行 `scripts/settle_forward_predictions.ps1`（settle append-only）。
4. 定期檢視 `FORWARD_SHADOW_STATUS.json`（累積 N/MAE/MASE/direction_accuracy）。

**注意**：forward evidence 至少要 n≥20（TOO_EARLY）才開始有意義，n≥150 才 SUBSTANTIAL_FORWARD。這需要數月真實交易日。

---

## Release 狀態（誠實）

- Research system validated ✓
- Historical statistical signal found（VAR 62.2%）✓
- No executable economic strategy edge ✓
- Forward validation active/pending ✓

**不得在任何 README/docs 宣稱：profitable / winning strategy / trading edge / production alpha。**
