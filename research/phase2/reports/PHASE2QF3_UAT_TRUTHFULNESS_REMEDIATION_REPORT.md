# PHASE 2Q-F.3 — Manual UAT Truthfulness Remediation + OSE Direct/Proxy Separation + Validation Evidence Isolation + Answer Contract Hardening

- gate：**PHASE2QF3_RUNTIME_TRUTH_PASS**（0 Critical / 0 High）
- build_id：`bc9bc59b0d970cab`
- 版本：`v2.0.0-rc1`（不 tag / release / retag）

## 12 問答（§51）

1. **OSE/TSE 怎麼混到？** `^N225` 一直用 XTKS（TSE cash）日曆；但 OSE Micro 沒有獨立 derivatives 日曆，packet 只寫「may differ」文字，LLM 無法 machine-readable 區分。修：新增 `next_ose_derivatives_sessions()` + packet 輸出 `direct_next_sessions` / `proxy_model_target_dates`。

2. **9/21–9/23 OSE 是否可交易？** 是。JPX Holiday Trading：2026-09-21/22/23 OSE derivatives OPEN，但 TSE cash（XTKS）closed。已寫入 `config/ose_derivatives_calendar.yaml`（source: JPX official）。

3. **^N225 forecast 為何不能冒充 Micro？** 因為是 PROXY（不同標的/日曆/資料源）。packet 新增 `direct_micro_forecast_status=NOT_AVAILABLE`；`^N225` 只標 `PROXY_MODEL_REFERENCE`。

4. **202703 settlement 為何被錯選？** `_load_latest_micro_settlement()` 對最新 date 直接 `iloc[-1]`，同一天 4 active contracts 時拿到最後一列（202703 遠月）。修：`_select_front_contract()`（FRONT_NEAREST_LISTED = min YYYYMM），deterministic 不依 row order。

5. **pytest 如何污染 TS validation DB？** `TsValidationStore` 改用 `resolve_db_path()` 後，測試的 `monkeypatch project_root` 失效，synthetic fixture 寫進 real DB。修：`tests/conftest.py` session autouse fixture 把 `MARKET_AI_DATA_ROOT` 指到 session temp。

6. **多少 synthetic rows 被 quarantine？** **8 rows**（chronos-2/^N225/n_origins=3/n_oos=10/mase=0.9/coverage=0.75）。`scripts/audit_validation_store.py --apply` 先 backup 再標 `run_kind=TEST_FIXTURE`。剩 4 筆 legitimate。

7. **MODEL_PREDICTIVE_GATE 清理後真實狀態？** `TsValidationStore.latest()` 現在 filter 掉 TEST_FIXTURE，gate 只讀 RUNTIME_VALIDATION；清理後 chronos-2/timesfm 無 synthetic evidence → gate 回到 UNPROVEN（不再被 synthetic 誤升）。

8. **75% 是什麼 metric？** `interval_coverage=0.75` = quantile interval 覆蓋率，**不是** direction accuracy。不得混稱（§7/§32）。

9. **Forward true evidence N？** `forward_evidence_n=0`（17 registered/pending，0 settled）。registered/pending ≠ validated forward evidence。

10. **HIGH AGREEMENT ambiguity 如何修？** `ensemble.py` 新增 `validated_direction_agreement`（只算 eligible voters，0 → N/A）；raw agreement 改名 `legacy_raw_unvalidated_agreement`。

11. **Taiwan weekend bar 如何處理？** `YFinanceProvider` 新增 `^TWII`/`*.TW`/`*.TWO` → `Asia/Taipei`（§28）。週末 bar 標 anomaly（§29 記錄，不當 official trading date）。

12. **是否還會輸出 buy/sell advice？** 否。Skills + System Prompt V4.1 已明寫「不得輸出任何交易建議」「research reference only」，且 support/resistance `NOT_AVAILABLE` 直接 N/A，不由 P10/P90 生成。

## 其他修正

- `get_research_gates()` 新增 `training_review`（auto_train=false、immediate_retrain_authorized=false、manual_approval_required=true）。
- `scripts/audit_runtime_evidence.py`（§47）：檢查 runtime evidence store 無「未 quarantine」的 synthetic fixture。
- `http_client.CACHE_ROOT` 改 lazy `data_root()`（尊重 test isolation）。

## Validation

- **full default pytest：781 passed, 20 deselected**（772 + 9 new test_phase2qf3）。
- test evidence isolation：pytest 前後 real runtime DB（ts_validation/performance/market）row-count 不變。
- audit_runtime_evidence：PASS（無未 quarantine synthetic）。docs links OK。secret scan 0 真實 secret。

## Manual UAT

```
MANUAL_CHERRY_UAT = RETEST_REQUIRED
```

使用者必須重新跑 5 cases（health / Osaka / 2330.TW / TAIEX / validation+retraining）。

## 禁區未動

不 new model / training / fine-tuning / strategy optimization / broker / live trading / tag / release / retag。
