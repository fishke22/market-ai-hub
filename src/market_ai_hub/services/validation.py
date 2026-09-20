"""時間序列 validation framework（V1 remediation + V1.1 OOS pipeline）。

Naive baselines（與模型共用同一 symbol / window / horizon）：
- last_price_naive / drift_baseline / moving_average_baseline

V1.1 OOS validation pipeline（rolling origins, no look-ahead, calendar-aware）：
- 多個 rolling origins，每個 origin 用固定 history 預測下一 bar
- 比較 3 個 baselines：MAE / RMSE / MASE
- predictive interval（p10-p90 nominal 80%）empirical coverage / width / calibration_error
- 輸出決定 promotion：deterministic thresholds 寫在 PROMOTION_RULES（不是 LLM 臨時決定）
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from market_ai_hub.config.settings import project_root

# ── deterministic promotion rules（code 內，禁止 LLM 臨時改）──
PROMOTION_RULES: dict = {
    "UNVALIDATED_TO_EXPERIMENTAL": {
        "min_rolling_origins": 3,
        "min_oos_samples": 10,
        "must_beat_baseline": "last_price_naive",
        "metric": "mae",
        "min_horizons_checked": 1,
        "reproducible_seed": 42,
    },
    "EXPERIMENTAL_TO_VALIDATED": {
        "min_rolling_origins": 8,
        "min_oos_samples": 50,
        "must_beat_baselines": ["last_price_naive", "drift"],
        "metric": "mase",
        "mase_max": 1.0,
        "min_windows": 2,  # 至少兩個不同日期 window
    },
}


def last_price_naive(series: pd.Series, steps: int) -> float:
    return float(series.iloc[-1])


def drift_baseline(series: pd.Series, steps: int) -> float:
    rets = series.pct_change().dropna()
    drift = float(rets.mean()) if len(rets) else 0.0
    return float(series.iloc[-1] * (1 + drift) ** steps)


def moving_average_baseline(series: pd.Series, steps: int, window: int = 20) -> float:
    ma = series.rolling(window).mean().iloc[-1]
    if pd.isna(ma):
        return float(series.iloc[-1])
    return float(ma)


def naive_forecast_path(series: pd.Series, steps: int) -> dict[str, list[float]]:
    last = float(series.iloc[-1])
    rets = series.pct_change().dropna()
    drift = float(rets.mean()) if len(rets) else 0.0
    path = [last * (1 + drift) ** k for k in range(1, steps + 1)]
    return {"last_price": [last] * steps, "drift": path}


def evaluate_against_baselines(
    symbol: str,
    actuals: np.ndarray,
    prev_closes: np.ndarray,
    model_forecasts: list[float],
    steps: int,
) -> dict:
    """對同一批 OOS 樣本比較模型與 naive baselines。"""
    actuals = np.asarray(actuals, dtype=float)
    prev = np.asarray(prev_closes, dtype=float)
    fc = np.asarray(model_forecasts, dtype=float)
    n = len(fc)
    if n == 0:
        return {"n_oos": 0, "status": "INSUFFICIENT_DATA"}

    def _err(a, p):
        e = np.abs(a - p)
        return float(np.mean(e)), float(np.sqrt(np.mean(e**2)))

    model_mae, model_rmse = _err(actuals, fc)
    naive_mae, naive_rmse = _err(actuals, prev)
    mase = model_mae / naive_mae if naive_mae > 0 else float("nan")

    drift_preds = np.array([drift_baseline(pd.Series(actuals[: i + 1] if i >= 0 else [prev[0]]), 1) for i in range(n)])
    drift_mae = float(np.mean(np.abs(actuals - drift_preds))) if n else float("nan")

    ma20_preds = np.array([moving_average_baseline(pd.Series(np.concatenate([[prev[i]], actuals[:i]])) if i > 0 else pd.Series([prev[i]]), 1, window=min(20, i + 1)) for i in range(n)])
    ma20_mae = float(np.mean(np.abs(actuals - ma20_preds))) if n else float("nan")

    dir_actual = np.sign(actuals - prev)
    dir_pred = np.sign(fc - prev)
    dir_hits = (dir_actual == dir_pred) & (dir_actual != 0)
    dir_acc = float(dir_hits.mean()) if len(dir_hits) else float("nan")

    return {
        "symbol": symbol,
        "horizon_steps": steps,
        "n_oos": int(len(dir_hits)),
        "status": "OK",
        "model": {"mae": model_mae, "rmse": model_rmse, "mase": mase, "direction_accuracy": dir_acc},
        "last_price_naive": {"mae": naive_mae, "rmse": naive_rmse, "mase": 1.0},
        "drift_baseline": {"mae": drift_mae},
        "moving_average_baseline": {"mae": ma20_mae},
        "beats_naive_mae": model_mae < naive_mae,
        "beats_drift_mae": model_mae < drift_mae,
    }


def run_ts_oos_validation(
    adapter,
    model: str,
    symbol: str,
    closes: pd.Series,
    n_origins: int = 5,
    history_len: int = 128,
) -> dict:
    """Rolling-origin OOS validation（no look-ahead）。

    每個 origin：用 origin 前 history_len 根 bars 預測下一根；
    interval 用該次預測的 p10/p90 檢查 coverage。
    """
    n = len(closes)
    if n < history_len + n_origins + 2:
        return {"status": "INSUFFICIENT_DATA", "symbol": symbol, "n_bars": n}

    positions = np.linspace(history_len, n - 2, n_origins, dtype=int)
    forecasts, actuals, prevs, p10s, p90s = [], [], [], [], []
    for pos in positions:
        ctx = closes.iloc[pos - history_len:pos]
        r = adapter.predict(ctx, horizon=1)
        path = r["path"]
        forecasts.append(path["p50"][-1])
        p10s.append(path["p10"][-1])
        p90s.append(path["p90"][-1])
        actuals.append(float(closes.iloc[pos + 1]))
        prevs.append(float(closes.iloc[pos]))

    ev = evaluate_against_baselines(symbol, np.asarray(actuals), np.asarray(prevs), forecasts, steps=1)

    # interval coverage：nominal p10-p90 = 80% 中央區間
    lo = np.asarray(p10s, dtype=float)
    hi = np.asarray(p90s, dtype=float)
    act = np.asarray(actuals, dtype=float)
    inside = (act >= lo) & (act <= hi)
    coverage = float(inside.mean())
    width = float(np.mean((hi - lo) / act))
    calibration_error = abs(coverage - 0.8)

    result = {
        "status": "OK",
        "model": model,
        "symbol": symbol,
        "n_origins": int(len(positions)),
        "history_len": history_len,
        "window": {"start": str(closes.index[0].date()), "end": str(closes.index[-1].date())},
        "eval": ev,
        "interval": {
            "nominal_level": 0.8,
            "coverage": coverage,
            "width_mean_rel": width,
            "calibration_error": calibration_error,
        },
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }
    return result


def determine_validation_status(result: dict) -> tuple[str, list[str]]:
    """Deterministic promotion（PROMOTION_RULES）。回傳 (status, reasons)。"""
    reasons: list[str] = []
    if result.get("status") != "OK":
        return "UNVALIDATED", [f"validation run not OK: {result.get('status')}"]

    n_origins = int(result.get("n_origins", 0))
    ev = result.get("eval", {})
    n_oos = int(ev.get("n_oos", 0))
    beats_naive = bool(ev.get("beats_naive_mae", False))
    mase = ev.get("model", {}).get("mase")

    exp_rule = PROMOTION_RULES["UNVALIDATED_TO_EXPERIMENTAL"]
    ok_exp = (
        n_origins >= exp_rule["min_rolling_origins"]
        and n_oos >= exp_rule["min_oos_samples"]
        and beats_naive
    )
    if not ok_exp:
        reasons.append(
            f"EXPERIMENTAL 門檻未達: origins={n_origins}/{exp_rule['min_rolling_origins']}, "
            f"n_oos={n_oos}/{exp_rule['min_oos_samples']}, beats_naive={beats_naive}"
        )
        return "UNVALIDATED", reasons

    reasons.append("EXPERIMENTAL 門檻達成（rolling origins + beats last-price naive）")

    val_rule = PROMOTION_RULES["EXPERIMENTAL_TO_VALIDATED"]
    beats_drift = bool(ev.get("beats_drift_mae", False))
    ok_val = (
        n_origins >= val_rule["min_rolling_origins"]
        and n_oos >= val_rule["min_oos_samples"]
        and beats_naive
        and beats_drift
        and (mase is not None and float(mase) <= val_rule["mase_max"])
    )
    if not ok_val:
        reasons.append(
            f"VALIDATED 門檻未達（origins={val_rule['min_rolling_origins']}, n={val_rule['min_oos_samples']}, "
            f"MASE<={val_rule['mase_max']}, beat drift 要求）；維持 EXPERIMENTAL"
        )
        return "EXPERIMENTAL", reasons

    reasons.append("VALIDATED 門檻達成")
    return "VALIDATED", reasons


class TsValidationStore:
    """TS validation run 持久化（非破壞性：新 table）。"""

    def __init__(self) -> None:
        from market_ai_hub.config.runtime_paths import resolve_db_path

        self.db_path = resolve_db_path("ts_validation.duckdb")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _conn(self):
        return duckdb.connect(str(self.db_path))

    def init(self) -> None:
        with self._conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    model VARCHAR, symbol VARCHAR, validated_at TIMESTAMP,
                    n_origins BIGINT, n_oos BIGINT, model_mae DOUBLE, naive_mae DOUBLE,
                    mase DOUBLE, direction_accuracy DOUBLE,
                    interval_coverage DOUBLE, interval_calibration_error DOUBLE,
                    beats_naive BOOLEAN, beats_drift BOOLEAN,
                    result_json VARCHAR
                )
                """
            )
            # §4：provenance / run_kind（RUNTIME_VALIDATION / TEST_FIXTURE / HISTORICAL_IMPORT）
            try:
                con.execute(
                    "ALTER TABLE runs ADD COLUMN run_kind VARCHAR DEFAULT 'RUNTIME_VALIDATION'"
                )
            except Exception:
                pass  # column already exists

    def save(self, result: dict, status: str, run_kind: str = "RUNTIME_VALIDATION") -> None:
        self.init()
        ev = result.get("eval", {})
        iv = result.get("interval", {})
        with self._conn() as con:
            con.execute(
                """INSERT INTO runs
                   (model, symbol, validated_at, n_origins, n_oos, model_mae, naive_mae,
                    mase, direction_accuracy, interval_coverage, interval_calibration_error,
                    beats_naive, beats_drift, result_json, run_kind)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    result.get("model"), result.get("symbol"),
                    datetime.now(timezone.utc),
                    int(result.get("n_origins", 0)), int(ev.get("n_oos", 0)),
                    ev.get("model", {}).get("mae"), ev.get("last_price_naive", {}).get("mae"),
                    ev.get("model", {}).get("mase"), ev.get("model", {}).get("direction_accuracy"),
                    iv.get("coverage"), iv.get("calibration_error"),
                    bool(ev.get("beats_naive_mae")), bool(ev.get("beats_drift_mae")),
                    json.dumps(result, ensure_ascii=False, default=str),
                    run_kind,
                ],
            )

    def latest(self, model: str, symbol: str, include_test_fixture: bool = False) -> dict | None:
        self.init()
        q = "SELECT * FROM runs WHERE model=? AND symbol=?"
        if not include_test_fixture:
            q += " AND (run_kind IS NULL OR run_kind != 'TEST_FIXTURE')"
        q += " ORDER BY validated_at DESC LIMIT 1"
        with self._conn() as con:
            df = con.execute(q, [model, symbol]).df()
        if df.empty:
            return None
        r = df.to_dict("records")[0]
        try:
            r["result"] = json.loads(r.get("result_json") or "{}")
        except json.JSONDecodeError:
            r["result"] = {}
        return r
