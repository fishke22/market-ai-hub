# PHASE 2Q-F.4 — Runtime Output Contract Enforcement + Proxy/Direct Presentation Hardening + Taiwan Session Filter Coverage

- gate：**PHASE2QF4_RUNTIME_OUTPUT_PASS**（0 Critical / 0 High）
- build_id：`cabed392964fb6de`
- 版本：`v2.0.0-rc1`（不 tag / release / retag）

## 9 問答（§34）

1. **為何 F3 後仍把 proxy 說成 Micro？** 因為 payload 沒有 machine-readable 的「direct vs proxy」分隔，LLM 仍要自行解讀 legacy 混雜欄位。修：packet 新增 `direct_micro_forecast_status=NOT_AVAILABLE` + `display_policy`；predict_* 輸出 `forecast_scope=PROXY_MODEL_REFERENCE` / `do_not_relabel_as_direct=true`。

2. **哪些 misleading fields 從 compact payload 移除？** `model_agreement`（raw）已標 `legacy_raw_unvalidated_agreement` + `validated_direction_agreement` 分離；新增 authoritative `direction_status` / `direction_value`（0 votes → None）。`class_probabilities` 標 uncalibrated，default 不當 probability。

3. **uncalibrated scores 現在如何呈現？** 只標 `raw_class_scores` / `raw_argmax_direction`（research_only），不得稱 probability。

4. **0 eligible votes 是否還能看到 HIGH/MEDIUM？** 否。`validated_direction_agreement=N/A`；`direction_status=NO_VALIDATED_MODEL_CONSENSUS`；raw agreement 改 `legacy_raw_unvalidated_agreement`（不當 consensus）。

5. **OSE / XTKS 兩組日期是否完全分開？** 是。Osaka packet `direct_next_sessions`（OSE derivatives，含 9/21-23 holiday trading）與 `proxy_model_target_dates`（XTKS，9/24 起）分開且 machine-readable。

6. **TAIEX 47368.04 來源是否為 invalid weekend bar？** 是（先前對應 2026-09-20 Sunday）。修：`sanitize_daily_exchange_sessions()` 排除非 XTAI session 的 daily bars。

7. **哪些 code paths 漏掉 session filter？** `_index_proxy_reference`（^TWII）、`_taiwan_stock_reference` yfinance fallback 原先未 filter。修：兩者皆套 `sanitize_daily_exchange_sessions`，並加 `reference_trading_date` / `reference_session_valid=true`。

8. **修後 last valid TAIEX reference/date？** Friday 47180.75（週日 row 被排除）；`reference_session_valid=true`。

9. **Case 5 是否保持 PASS？** 是。`MODEL_PREDICTIVE_GATE=UNPROVEN`、Forward N=0、REVIEW_ONLY、AUTO_TRAIN/FINE_TUNE/PROMOTE=false 皆未改。

## 交付

- `ensemble.py`：`direction_status` / `direction_value`（單一 authoritative contract）。
- `calendar.py`：`sanitize_daily_exchange_sessions()`（排除 invalid XTAI/XTKS session bars）。
- `packet/builder.py`：`_index_proxy_reference` / `_taiwan_stock_reference` 套 session filter；`display_policy`。
- `mcp/server.py`：`predict_ensemble` 加 `forecast_scope` 等 scope 欄位。
- `scripts/assert_uat_semantics.py`（forbidden combination assertions）。
- `tests/test_phase2qf4.py`（10 golden tests）。

## Validation

- **full default pytest：791 passed, 20 deselected**（781 + 10 new）。
- assert_uat_semantics：PASS。
- audit_runtime_evidence：PASS（pytest 不污染 real runtime DB）。
- docs links / secret scan：PASS。

## Manual UAT

```
MANUAL_CHERRY_UAT = RETEST_REQUIRED
```

使用者重新跑同樣 5 cases。Agent 不得自行標 PASS。

## 禁區未動

不 new model / training / fine-tuning / strategy optimization / broker / live trading / tag / release / retag。
