# Model Adapters（統一模型介面）

Phase 2D 的**統一 Model Adapter Contract**（`research/tournament/adapter.py`）。

## Adapter 介面

```python
class ModelAdapter(ABC):
    name: str
    task: str            # "price" | "direction"
    revision: str
    training_cutoff: datetime | None

    def fit(self, df)            # 用 OHLCV df 訓練（zero-shot 模型為 no-op）
    def forecast(self, df, steps) -> ForecastResult
    def metadata(self) -> dict
    def supported_horizons(self) -> list[str]
    def release(self)            # 釋放 GPU（多模型避免 VRAM 常駐）
```

## ForecastResult 欄位（依模型能力，不造假）

| 欄位 | PRICE_FORECAST | DIRECTION_CLASSIFICATION |
|------|----------------|--------------------------|
| `point` | ✅ | ❌（None） |
| `p10/p50/p90` | 只有真 predictive distribution 才回 | ❌（None） |
| `forecast_path` | ✅（可選） | ❌ |
| `quantile_valid` | p10≤p50≤p90 才 true | None |
| `class_label` | ❌ | ✅（-1/0/1） |
| `raw_scores` | ❌ | ✅（可選） |
| `probability_calibrated` | ❌ | ✅（未校準 = false） |
| `calibration_metadata` | ❌ | ✅（method 等） |

- **PRICE_FORECAST**：point / p10 / p50 / p90 / forecast_path。
  只有真的 predictive distribution 才回 predictive quantiles。
- **DIRECTION_CLASSIFICATION**：class_label / raw_scores / probability_calibrated /
  calibration_metadata。**不得製造假的價格 quantiles。**

## 已接入 Adapter

| Adapter | task | 來源 |
|---------|------|------|
| `ChronosAdapter` | price | chronos-forecasting（V1） |
| `TimesFMAdapter` | price | timesfm3（V1） |
| `FinCastAdapter` | price | 隔離 venv bridge（point only） |
| `XGBoostAdapter` / `LightGBMAdapter` | direction | V1 baseline_ml |
| naive baselines（last price / random walk / drift / MA / seasonal） | price | 內建 |
| majority_class / always_flat | direction | 內建 |
| statistical（ridge / var / dynamic_factor / kalman） | price | sklearn / statsmodels |

## Baselines（永遠保留）

`research/tournament/baselines.py`：Tournament 永遠保留 naive + statistical baselines。
AI 模型打不贏 baseline 就照實呈現，不得因模型較新而提高排名。

## Challenger（未接入，標記原因）

- Kronos-TW（CHALLENGER，license unknown、訓練截止 2024-12-31）
- Sundial（BLOCKED_LICENSE，gated repo）
- Moirai-2（BLOCKED_LICENSE，gated + 非商業權重）
- TinyTimeMixer（CHALLENGER，granite-tsfm 依賴較重，adapter 未接）
- NHITS / NBEATSx（CHALLENGER，neuralforecast 已安裝，adapter 未接）

詳見 `config/model_registry.yaml` 與 `docs/MODEL_LICENSE_MATRIX.md`。
