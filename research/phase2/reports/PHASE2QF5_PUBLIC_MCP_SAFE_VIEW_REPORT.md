# PHASE 2Q-F.5 — Public MCP Safe View + Position-Aware Research Guard + Manual UAT Contract Closure

- gate：**PHASE2QF5_PUBLIC_SAFE_PASS**（0 Critical / 0 High）
- build_id：`4286537b8a8ae4f7`
- 版本：`v2.0.0-rc1`（不 tag / release / retag）

## 8 問答（§37）

1. **F4 有 safe fields，Cherry 為何還能輸出 probabilities？** 因為 safe fields 只加在 `get_analysis_packet` 的 packet，但 Cherry 可直接呼叫 `predict_chronos/timesfm/ensemble`、`analyze_*`，那些工具仍回傳 raw `class_probabilities` / `direction` / `model_agreement`，未經 public sanitizer。

2. **哪些 raw MCP paths 繞過 public contract？** `predict_chronos` / `predict_timesfm` / `predict_ensemble`（回傳 `fo.model_dump()` 含 raw classifier/ensemble fields）。修：全部套 `sanitize_forecast_dump()` / `sanitize_ensemble_dump()`。

3. **HIGH/MEDIUM 從哪個欄位進回答？** `model_metadata.model_agreement`（raw，由全部 unvalidated component direction 計算）。修：public view 移除 `model_agreement` / `legacy_raw_unvalidated_agreement`，只留 `validated_direction_agreement`。

4. **2330 support/resistance 從哪個 path 被重新產生？** Skill 自行從 P10/P90 推導。修：`quantiles` → `predictive_quantile_range`，public 移除 support/resistance alias；Skill 只 render authoritative fields。

5. **TAIEX 47368.04 是 cache 還是 unsanitized path？** 兩者皆可能。修：`SESSION_FILTER_VERSION` 進 forecast cache key（舊 unsanitized cache 不得 reuse）+ `sanitize_daily_exchange_sessions()` 已套 reference path。

6. **Micro 為何被寫成 Mini？** 無 canonical display-name resolver。修：`canonical_instrument_name()`（Micro/Mini/Large/^N225/TAIEX 正式名）。

7. **21 MCP tools 哪些 public-safe 哪些 audit-only？** `predict_chronos/timesfm/ensemble` 現 public-safe（sanitized）；`get_analysis_packet` 已 public-safe；raw classifier/ensemble 欄位只在 `detail_level=audit` 或 explicit diagnostic 才出現。

8. **position-aware request 現在如何處理？** 新增 `position_guidance_policy`（mode=RISK_ANALYSIS_ONLY，personalized_trade_action=PROHIBITED）；只允許 exposure/PnL sensitivity/scenario analysis；禁止 ADD/REDUCE/STOP/TAKE_PROFIT/ORDER_SIZE。

## 交付

- `services/public_view.py`（新）：`sanitize_forecast_dump()` / `sanitize_ensemble_dump()` / `canonical_instrument_name()` / `position_guidance_policy()`。
- `mcp/server.py`：predict_chronos/timesfm/ensemble 套 sanitizer。
- `packet/schema.py` + `builder.py`：`position_guidance_policy`。
- `services/forecast_cache.py`：`SESSION_FILTER_VERSION` 進 cache key。
- `scripts/assert_uat_semantics.py`：新增 position guard assertions。
- `tests/test_phase2qf5.py`（13 tests，含 Case 6 exposure math 23×10=230）。

## Case 6 處理（§21/§24）

- Exposure math 允許：Micro multiplier JPY 10/point，23 口 → 每 point JPY 230、每 100 points JPY 23,000。
- 禁止：加碼 N 口 / 停損 X / 停利 X / 獲利了結 X% / 攤平 / 低接 / 追高（即使加「僅供參考」）。
- Scenario 表只命名 price / difference / PnL，不得命名 stop / target / take profit / entry。

## Validation

- **full default pytest：804 passed, 20 deselected**（791 + 13 new）。
- assert_uat_semantics：PASS（含 position guard）。
- audit_runtime_evidence：PASS（pytest 零污染 real runtime DB）。
- docs links / secret scan：PASS。

## Manual UAT

```
MANUAL_CHERRY_UAT = RETEST_REQUIRED
```

使用者再跑 5 cases + 第 6 題（神達 + 大阪 Micro 23 口多單加碼/獲利了結）。六題全過才 `FINAL_UAT_PASS`。

## 禁區未動

不 new model / training / fine-tuning / strategy optimization / broker / live trading / tag / release / retag。
