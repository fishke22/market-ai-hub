# Model Validation Audit（模型驗證稽核）

輸出模型的驗證狀態，**不得用「模型很先進」作為評分理由**。

## 觸發
使用者要稽核某個模型的預測能力、驗證狀態、是否值得信任。

## 工作流程
1. 呼叫 `get_model_leaderboard(target=..., horizon=...)` 取得模型績效。
2. 呼叫 `get_forward_test_status()` 取得 forward test 註冊／結算狀態。
3. 需要資料覆蓋時呼叫 `get_data_coverage()`。

## 稽核欄位
| 欄位 | 說明 |
|---|---|
| model | 模型名 |
| target / horizon | 標的與預測期間 |
| sample size | 樣本數（樣本不足不得宣稱） |
| MASE | 相對 baseline 誤差 |
| baseline | 對比 baseline（BEST_BASELINE） |
| Forward Test | 是否有 forward paper 證據 |
| regime evidence | 各 regime 樣本是否足夠（不足→REGIME_EVIDENCE_INSUFFICIENT） |
| calibration | 區間／機率校準 |
| status | UNVALIDATED / EXPERIMENTAL / VALIDATED |

## 判定規則
- 打不贏 baseline → 不給正向評分，允許 BASELINE_DOMINANT。
- 樣本不足（如 <30）→ 不得稱 EDGE_FOUND 或 VALIDATED。
- 未 forward-validated → 標 `UNVALIDATED_FORWARD`。
- 不得以「模型新、參數多、架構複雜」當作可信度理由。
