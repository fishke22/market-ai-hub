# Out-of-Sample Validation Standard

**Phase 2Q-C** — 三市場 OOS 驗證標準。

## 核心

OOS = 模型從未在 training/validation 看過的未來資料。時間序列驗證一律 chronological。

## Split（§9）

- chronological split + walk-forward / rolling-origin。
- 禁止 random shuffle 作為主要驗證。

## Leakage Invariants（§32）

| invariant | 意義 |
|-----------|------|
| future_row_not_in_train | 任何 future row 不得在 train set |
| feature_asof_before_target | feature 的 as-of 必須早於 target |
| corporate_action_adjustment_causal | 除權息調整必須 causal（不 forward-fill future price） |
| validation_not_final_test | validation 區不得含 final OOS |
| hyperparameter_tuning_no_test_access | tuning 不得 access test |
| walkforward_origin_strict | 每 origin fit only past |
| proxy_not_direct | proxy 不得冒充 direct |
| target_family_isolated | 各市場證據隔離 |

## Evidence per Target（§21）

evidence 依 target_family / target / horizon 隔離。禁止 Osaka evidence 替 Taiwan 背書。
各市場 Forward N 不得混成單一 sample count（§26）。

## Dataset / License（§30/§31）

- 每個 training dataset 記錄 source / license / redistribution / local_only / date range / hash / target semantic。
- Private / licensed raw data 不得 GitHub。
- evidence 綁 dataset_version / feature_version / model_version / protocol_version / build_id，否則不可重現。

## Strategy Validation（§27/§28）

- 買賣策略與 forecast validation 分開。
- 至少：signal creation time / execution time / spread / fees / slippage / turnover / drawdown / subperiod / regime。
- Forecast 很準仍可能 NO_ECONOMIC_EDGE。
- TAIWAN_INDEX 策略 execution 必須明確指定 TX / MTX / TMF 之一，不得用 TAIEX 點位假裝成交。

## 目標（§35）

本標準目的**不是**找會賺錢的模型；若測出 NO_EVIDENCE 仍是正確結果。
