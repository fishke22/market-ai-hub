# Scenario Engine（情境引擎）

`forecast/scenario.py`。

## 輸入
current cross-asset state + regime + event state + joint forecast distribution。

## 輸出
多條 `ScenarioPath`，包含：
- scenario_id / horizon
- NQ_path / ES_path / SOX_path / USDJPY_path / VIX_path / rates_path
- nikkei_distribution
- scenario_source / scenario_weight / weight_calibration_status

## Scenario 型別（由 feature/regime rule 產生，非 LLM 編數字）
```
BASE / RISK_ON / RISK_OFF / JPY_STRENGTHEN / JPY_WEAKEN /
VOL_SHOCK / RATES_SHOCK / EVENT_SHOCK
```
每個 type 對應一組 deterministic cross-asset shock（`SCENARIO_SHOCKS`），
scenario 由這些 rule 產生，不得由 LLM 隨意編數字。

## Scenario weight 語義（非常重要）
- `scenario_weight` 未經 OOS calibration → 只能稱 `scenario_weight`，標 `UNVALIDATED_WEIGHT`。
- **不得稱「機率／發生機率／成功率」**。
- 只有經 Forward/OOS calibration 才可標 `CALIBRATED_PROBABILITY`。
