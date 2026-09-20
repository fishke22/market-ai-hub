# PHASE2D1_CHALLENGER_ACTIVATION_REPORT

日期：2026-09-19
範圍：`D:\MARKET_AI_HUB`（Phase 2D.1 — Challenger Activation + Data Sanity Hardening）

> 本報告只呈現完全相同的 OOS / walk-forward 條件（n_forecast_origins=4）下的實測結果。
> 樣本小（4 origins），**不足以做強結論**；不寫「預測能力已提高」這類無充分證據的宣稱。

## 1–7. Challenger 狀態

| Challenger | 狀態 | 說明 |
|-----------|------|------|
| **NHITS** | ✅ ACTIVATED | neuralforecast 3.2.2，fit-on-the-fly，已進 Tournament |
| **NBEATSx** | ✅ ACTIVATED | neuralforecast 3.2.2（identity-only block），已進 Tournament |
| **FinCast** | ✅ PARTIAL（bridge） | 已進 Tournament（point only） |
| Kronos-TW | CHALLENGER（未啟用） | license 已修正 MIT；adapter 未建（自訂 tokenizer+predictor class，高工） |
| Sundial | CHALLENGER（未啟用） | license 已修正 Apache-2.0；公開下載路徑已驗證；adapter 未建（trust_remote_code） |
| TinyTimeMixer (TTM) | DEFERRED_DEPENDENCY_CONFLICT | granite-tsfm 將 torch 釘在 2.11（與 V1 cu130 衝突），未強裝 |
| Moirai-2 | NONCOMMERCIAL_RESEARCH_ONLY | CC-BY-NC-4.0；uni2ts 未裝；adapter 未建 |

## 8. License 修正

- Kronos-TW-Predictor / Kronos-TW-Tokenizer：**MIT**（training 2010-01-01 ~ 2024-12-31）。
- Moirai-2：**CC-BY-NC-4.0**（`Salesforce/moirai-2.0-R-small`），NONCOMMERCIAL_RESEARCH_ONLY，不得重新發布。
- Sundial：**Apache-2.0**（`thuml/sundial-base-128m`，公開）。
- TinyTimeMixer：**Apache-2.0**。
- 先前「gated 401」是 **repo id 打錯**（`thuml/Sundial`→`thuml/sundial-base-128m`；`Salesforce/Moirai2`→`Salesforce/moirai-2.0-R-small`），
  非真的 gating。

## 9. Download blockers

無（全部公開）。未下載：Kronos 425MB、Sundial 513MB（adapter 未建故未下載）、Moirai 45.6MB、TTM 4.6MB。

## 10. Dependency blockers

- TTM：`granite-tsfm` 會把 torch 降級 2.11（移除 cu130）→ 與 V1 衝突 → 已還原 torch，TTM 標 DEFERRED。
- Moirai：`uni2ts` 未安裝（避免類似 torch 衝突）。

## 11. VRAM / runtime

- NHITS / NBEATSx：CPU fit ~1–2s/origin，無 GPU 常駐。
- 無 OOM（已實測模型皆在 16GB 內）。

## 12. 3706 frozen-target root cause

**TWSE OpenAPI `STOCK_DAY_ALL` 對所有歷史日期都回傳最新一個交易日**（實測：請求 1150601/1150301/1141201 都回 1150918）。
→ 原 `fetch_symbol_daily` 逐日迭代時，把「最新一天」的 OHLC 複製成整段序列（181 列全 80.5）。

## 13. 是否修復

✅ **已修復**。改為使用 TWSE 官方**單股 `STOCK_DAY`**（月線）endpoint，逐月拉取並正規化日期。
3706.TW 現在 244 列、unique_close=137、price_std=5.03（真實 OHLC 變動）。

## 14. 哪些 targets 可正式 Tournament

- `^N225`：VALID（std 7493）。
- `3706.TW`：**修復後 VALID**（std 5.03）。

## 15. 各 target/horizon 結果（n_forecast_origins=4）

| target/horizon | best baseline | best model | MASE(baseline) | MASE(model) | delta |
|----------------|---------------|------------|----------------|-------------|-------|
| ^N225 / 1d | seasonal_naive | chronos-2 | 0.774 | 0.884 | +0.142 |
| ^N225 / 5d | seasonal_naive | chronos-2 | 0.580 | 0.968 | +0.670 |
| 3706.TW / 1d | var | timesfm-3.0 | 0.933 | 1.094 | +0.172 |
| 3706.TW / 5d | drift | **nbeatsx** | 0.956 | **0.414** | **-0.567** |

- **nbeatsx 在 3706.TW/5d 真正打敗所有 baseline**（MASE 0.414，delta -0.57）——這是唯一 model 明確勝出的一格。
- chronos-2 仍穩定打敗 last-price naive（MASE<1），但**非**該 horizon 最佳（seasonal_naive 更強）。

## 16. 哪些模型值得進下一階段

- **nbeatsx**：3706.TW/5d 明確勝出（但樣本僅 4 origins，需 Forward Paper Test 累積更多樣本才可考慮 promotion）。
- **chronos-2**：持續打敗 last-price naive（4/4 horizon）。
- 結論：**尚無模型足以自動學習 promotion**（樣本不足，AUTO_PROMOTE=false 維持）。

## Tests

pytest 全部 **226 passed**（154 V1 + 12 2A + 12 2B + 17 2C + 16 2D + 15 2D.1）。
build_id 維持 `bbf3cb2f9a80d20e`（V1 correctness 未變）。

## Blockers

- TTM：torch 2.11 vs cu130 衝突（DEFERRED_DEPENDENCY_CONFLICT）。
- Kronos-TW / Sundial / Moirai adapter 未建（custom class loading / 依賴較重）。
- n_origins=4 樣本小，非最終排名。

## Gate

**PHASE2D1_PASS**：資料完整性通過（3706 修復）+ NHITS/NBEATSx 真正進入 Tournament + License metadata 正確。
