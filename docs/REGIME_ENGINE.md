# Regime Engine（市場狀態引擎）+ Event Engine（事件引擎）

Phase 2C 的 **程式化** 市場狀態判定。**不由 LLM 主觀決定**，閾值全部寫死在 code。

## MarketRegimeEngine（`regime/engine.py`）

輸入：panel DataFrame（columns = symbols，index = tz-aware datetime，值 = close）。
輸出 7 個 regime，每個含 `label / status / sample_size / evidence`：

| regime | 判定（deterministic） |
|--------|----------------------|
| `trend_regime` | ^N225 MA20 vs MA200：bull / bear / sideways |
| `volatility_regime` | ^N225 20d 實現波動率：low / normal / high / crisis |
| `risk_regime` | VIX 水準：risk_on(<15) / neutral(15–25) / risk_off(>25) |
| `rates_regime` | US10Y−US2Y 斜率：inverted / flat / normal + rising / falling |
| `fx_regime` | USDJPY 20d 報酬：usd_strength / jpy_strength / range |
| `event_regime` | 事件排程接近度：pre_event / event_window / post_event / none |
| `liquidity_regime` | 成交量百分位：liquid / normal / illiquid / unknown |

## Regime Protection（`regime/protection.py`）

- **minimum_sample_size**：樣本 < 門檻 → `status=REGIME_EVIDENCE=INSUFFICIENT`，不給 label、不調權重。
- **confidence interval**：比例用 Wilson CI、均值用 standard error（deterministic）。
- **shrinkage_to_global**：`(n·stat + k·global)/(n+k)`，樣本小時向全域先驗收縮，
  **不得用少量樣本大幅調權重**。

## Event Engine（`regime/events.py`）

- **Known events**：`event_phase(schedule_dates, as_of)` → `PRE_EVENT`（前 3 日）/
  `EVENT_WINDOW`（當日）/ `POST_EVENT`（後 3 日）/ `NONE`。
- **Breaking event**：`record_breaking_event(name, event_time)`；
  `stale_forecast_ids(forecasts, event_time)` 回傳 `information_cutoff < event_time` 的 forecast →
  標記 **FORECAST_STALE_AFTER_EVENT**。
- 觸發後流程（由 orchestration 層執行）：**refresh data → recompute regime → rerun forecast**。

## 使用

```python
from market_ai_hub.regime.engine import MarketRegimeEngine
from market_ai_hub.regime.events import EventEngine, event_phase

regimes = MarketRegimeEngine(minimum_sample_size=20).compute(panel, as_of=as_of)

eng = EventEngine()
eng.record_breaking_event("FOMC", event_time)
stale = eng.stale_forecast_ids(forecasts)  # 需 rerun 的 forecast ids
```

## 注意

- 全 deterministic、可重現；樣本不足誠實回 INSUFFICIENT。
- 本模組為 Phase 2C 新增，不改動 V1 核心（build_id 維持 `bbf3cb2f9a80d20e`）。
