# Model Validation Audit（模型驗證稽核）

## Purpose
稽核模型預測能力與驗證狀態。不得用「模型很先進」當評分理由。

## When to use
使用者要稽核某模型是否值得信任時。

## Required MCP
- `get_model_leaderboard`
- `get_forward_test_status`
- `get_data_coverage`（需要時）

## Workflow
1. `get_model_leaderboard(target=..., horizon=...)` 取績效。
2. `get_forward_test_status()` 取 forward test 狀態。
3. 輸出稽核表。

## Required checks
- sample size（不足不得宣稱）
- MASE（vs baseline）
- baseline 對比（打不贏 → BASELINE_DOMINANT）
- Forward Test（有無 forward paper 證據）
- regime evidence（不足 → REGIME_EVIDENCE_INSUFFICIENT）
- calibration

## Output structure
model / target / horizon / sample size / MASE / baseline / Forward Test / regime evidence / calibration / status。

## Failure handling
- 無資料 → 標 INSUFFICIENT，不猜。

## Do not rules
- 不得以「新、參數多、架構複雜」當可信度理由。
- 打不贏 baseline 不得給正向評分。
