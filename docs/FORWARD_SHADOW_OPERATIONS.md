# FORWARD SHADOW OPERATIONS（每日操作白話說明）

> Forward Shadow 是 research forecast 追蹤（不是 trading）。追蹤 VAR(1) forecast quality。

## 1. 前置：取得合法的 225LABO Micro 資料

225LABO 資料是**個人研究用**（僅下載者本人使用，不得散布）。新資料需**手動**從 225LABO 官方下載（不得用 scraper 自動抓取）。

把新下載的 `.zip` / `.xlsx` 檔案放到 private inbox：

```
D:\MARKET_AI_HUB_PRIVATE_INBOX\225labo\
```

## 2. Import 新資料

```powershell
scripts\import_latest_225labo_micro.ps1
```

- detect 新檔案 → validate（instrument / date / timezone / tick / volume）→ hash → dedup → normalize → 更新 coverage。
- **incremental + idempotent**：同一檔案重跑不產生 duplicate。
- **source immutable**：原始檔保留在 archive，不 overwrite。
- schema 變更 → `IMPORT_REJECTED`（不會自動猜）。

## 3. 每日 forward cycle

```powershell
scripts\run_daily_forward_cycle.ps1
```

流程：ingest → freshness check →（若 FRESH）建立 forecast → settle 到期 forecast → 更新 status → 寫 summary。

只有 freshness = **FRESH** 才建立 forecast；否則 `FORECAST_SKIPPED_DATA_QUALITY`。

## 4. 看結果

```powershell
Get-Content FORWARD_DAILY_SUMMARY.md
Get-Content FORWARD_SHADOW_STATUS.json
```

- `FORWARD_DAILY_SUMMARY.md`：Data 狀態 / Forecast 今天 / Pending / Settled / Forward N / Evidence label。
- 無 BUY / SELL / LONG / SHORT。

## 5. PC 關機會怎樣

- **PC 關機時，該日 forecast 無法建立，且事後不能補成 forward**（只能標 `MISSED_FORWARD_ORIGIN`）。
- 可以補 market data，但該日 forecast 不算 forward evidence。
- 真正 forward evidence 必須在當時（收盤後、actual 未揭露前）建立。

## 6. 排程（opt-in only）

```powershell
scripts\register_forward_shadow_task.ps1   # 只建立 on-demand task，不自動 daily
```

- Windows Task Scheduler **預設 DISABLED**。只有明確執行才註冊，且只註冊手動觸發 task。
- 若要自動 daily，需自行編輯 trigger（本專案不自動啟用）。

## 7. 重要限制

- **Forward evidence 需累積真實交易日**：n < 20 = TOO_EARLY，n ≥ 150 = SUBSTANTIAL_FORWARD（需數月）。
- **Forecast 是 RESEARCH_FORECAST_ONLY / NON_EXECUTABLE_FORECAST_EDGE**，不是 trading signal。
- 資料 stale 時正確 skip，不硬產生 forecast。
