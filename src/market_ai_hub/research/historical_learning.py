"""Phase 2Q-C — Historical Learning + Walk-Forward + OOS validation framework.

三市場 primary target families 共用此框架。核心不變式：
- 時間序列嚴禁 random shuffle → chronological split + walk-forward / rolling-origin。
- 三資料區：TRAIN / VALIDATION / FINAL_OOS_HOLDOUT，時間隔離，不得 leakage。
- 每個 origin：fit only past → predict future → store immutable result → score after actual。
- Pre-register protocol：在看結果前固定 target/date range/horizons/baselines/metrics/models。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Callable, Any

import numpy as np
import pandas as pd


# ── 三資料區 ──
TRAIN = "TRAIN"
VALIDATION = "VALIDATION"
FINAL_OOS_HOLDOUT = "FINAL_OOS_HOLDOUT"


def three_zone_split(
    n: int,
    train_frac: float = 0.6,
    val_frac: float = 0.2,
) -> dict[str, tuple[int, int]]:
    """把 0..n 依時間切成 TRAIN / VALIDATION / FINAL_OOS（chronological，無 shuffle）。"""
    if n <= 0:
        raise ValueError("n must be > 0")
    train_end = int(n * train_frac)
    val_end = train_end + int(n * val_frac)
    return {
        TRAIN: (0, train_end),
        VALIDATION: (train_end, val_end),
        FINAL_OOS_HOLDOUT: (val_end, n),
    }


def zone_index(zone: str, n: int, **kw) -> np.ndarray:
    """回某區的 index 陣列。"""
    bounds = three_zone_split(n, **kw)
    a, b = bounds[zone]
    return np.arange(a, b)


def assert_no_zone_overlap(n: int, **kw) -> bool:
    b = three_zone_split(n, **kw)
    return (
        b[TRAIN][1] <= b[VALIDATION][0]
        and b[VALIDATION][1] <= b[FINAL_OOS_HOLDOUT][0]
    )


# ── pre-registration protocol ──
@dataclass
class ProtocolSpec:
    """在看結果前固定的 exam protocol。任何欄位變更 → protocol hash 變（不可變）。"""

    target_family: str
    target: str
    dataset_semantic: str
    date_range_start: str
    date_range_end: str
    horizons: list[str] = field(default_factory=lambda: ["1d"])
    baselines: list[str] = field(default_factory=lambda: ["LAST_VALUE", "ZERO_RETURN"])
    metrics: list[str] = field(default_factory=lambda: ["MAE", "RMSE", "MASE"])
    models: list[str] = field(default_factory=list)
    cost_assumptions: dict = field(default_factory=dict)
    regime_definitions: dict = field(default_factory=dict)
    success_criteria: dict = field(default_factory=dict)
    split_mode: str = "expanding"  # expanding | rolling
    n_origins: int = 5
    min_train: int = 60

    def protocol_hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ── walk-forward splits ──
def chronological_origins(
    n: int,
    n_origins: int = 5,
    min_train: int = 60,
    mode: str = "expanding",
    rolling_window: int | None = None,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """回 [(train_idx, test_idx), ...]。train 永遠在 test 之前（chronological）。

    - expanding：train 從 0 累積到 test_start。
    - rolling：train 只保留最近 rolling_window 根。
    無 leakage：test_start 嚴格大於所有 train index。
    """
    if n < min_train + n_origins:
        return []
    origins: list[tuple[np.ndarray, np.ndarray]] = []
    test_size = max(1, (n - min_train) // (n_origins + 1))
    for i in range(n_origins):
        test_start = min_train + i * test_size
        test_end = min(n, test_start + test_size)
        if test_end <= test_start or test_start >= n:
            break
        if mode == "rolling" and rolling_window:
            train_start = max(0, test_start - rolling_window)
        else:
            train_start = 0
        origins.append((np.arange(train_start, test_start), np.arange(test_start, test_end)))
    return origins


def assert_origins_no_leakage(origins: list[tuple[np.ndarray, np.ndarray]]) -> bool:
    """每個 origin：train max < test min（fit 只看到 past）。"""
    for train, test in origins:
        if len(train) == 0 or len(test) == 0:
            continue
        if train.max() >= test.min():
            return False
    return True


# ── baselines（§18）──
def naive_scale(series: np.ndarray, m: int = 1) -> float:
    """naive in-sample scale = mean(|Y_t - Y_{t-m}|) 只在 TRAINING history 上算。

    不得用 test actual 估 scale（§15/§19）。
    """
    s = np.asarray(series, dtype=float)
    if len(s) <= m:
        return float("nan")
    return float(np.mean(np.abs(s[m:] - s[:-m])))


def baseline_predictions(series: np.ndarray, n_steps: int, method: str, m: int = 1) -> np.ndarray:
    """產生 test 期 baseline 預測（只用 train series；§18）。"""
    s = np.asarray(series, dtype=float)
    if method in ("LAST_VALUE", "ZERO_RETURN"):
        # zero return == last value for level forecast
        return np.full(n_steps, s[-1])
    if method == "SEASONAL_NAIVE":
        if len(s) < m:
            return np.full(n_steps, np.nan)
        return np.asarray([s[-m - 1 + ((i % m))] if (i % m) < m else np.nan for i in range(n_steps)])
    if method == "DRIFT":
        if len(s) < 2:
            return np.full(n_steps, s[-1])
        step_change = (s[-1] - s[0]) / (len(s) - 1)
        return s[-1] + step_change * np.arange(1, n_steps + 1)
    raise ValueError(f"unknown baseline method: {method}")


# ── unified walk-forward runner ──
@dataclass(frozen=True)
class WalkForwardFold:
    """immutable fold result（fit past → predict future → 之後 score）。"""

    origin: int
    train_idx: tuple[int, ...]
    test_idx: tuple[int, ...]
    prediction: tuple[float, ...] | None = None
    score: dict = field(default_factory=dict)

    def model_dump(self) -> dict:
        d = asdict(self)
        d["prediction"] = list(d["prediction"]) if d["prediction"] is not None else None
        return d


class HistoricalWalkForwardProtocol:
    """統一 walk-forward / rolling-origin 框架（expanding / rolling）。

    run() 呼叫 model_fn(train_df) → fit → model.predict(test_features) → 存 immutable fold。
    scoring 由 caller 在實際值出現後呼叫 score()，不在 run() 內 peek 未來。
    """

    def __init__(self, spec: ProtocolSpec):
        self.spec = spec

    def run(
        self,
        df: pd.DataFrame,
        model_factory: Callable[[], Any],
        feature_cols: list[str],
        target_col: str,
    ) -> list[WalkForwardFold]:
        n = len(df)
        origins = chronological_origins(
            n, self.spec.n_origins, self.spec.min_train,
            mode=self.spec.split_mode,
        )
        folds: list[WalkForwardFold] = []
        for i, (train_idx, test_idx) in enumerate(origins):
            model = model_factory()
            train_df = df.iloc[train_idx]
            test_df = df.iloc[test_idx]
            model.fit(train_df[feature_cols].to_numpy(), train_df[target_col].to_numpy())
            preds = model.predict(test_df[feature_cols].to_numpy())
            folds.append(WalkForwardFold(
                origin=i,
                train_idx=tuple(int(x) for x in train_idx),
                test_idx=tuple(int(x) for x in test_idx),
                prediction=tuple(float(x) for x in np.asarray(preds).flatten()),
            ))
        return folds

    @staticmethod
    def score(folds: list[WalkForwardFold], df: pd.DataFrame, target_col: str, m: int = 1) -> dict:
        """實際值出現後才 score。

        每 fold 的 MASE denominator 只用該 fold TRAINING history 的 naive in-sample scale（§15）。
        不得跨 fold 邊界 diff，不得讓 future test observation 進 scaling denominator（§19）。
        回 aggregate + per-fold metrics（§17 fold-level auditability）。
        """
        fold_metrics: list[dict] = []
        mae_sum = 0.0
        rmse_sumsq = 0.0
        n_total = 0
        mase_num = 0.0
        mase_den = 0.0

        for fold in folds:
            train_series = df.iloc[list(fold.train_idx)][target_col].to_numpy(dtype=float)
            test_actual = df.iloc[list(fold.test_idx)][target_col].to_numpy(dtype=float)
            pred = np.asarray(fold.prediction or (), dtype=float)

            n_train = len(train_series)
            n_test = len(test_actual)
            if n_test == 0 or len(pred) != n_test:
                continue

            scale = naive_scale(train_series, m=m)  # training-only，不含 test
            err = pred - test_actual
            fold_mae = float(np.mean(np.abs(err)))
            fold_rmse = float(np.sqrt(np.mean(err ** 2)))
            fold_mase = fold_mae / scale if (scale and np.isfinite(scale) and scale > 1e-12) else float("inf")

            fold_metrics.append({
                "origin": fold.origin,
                "n_train": n_train,
                "n_test": n_test,
                "mae": fold_mae,
                "rmse": fold_rmse,
                "mase": fold_mase,
                "mase_scale": scale,
            })

            mae_sum += fold_mae * n_test
            rmse_sumsq += (fold_rmse ** 2) * n_test
            n_total += n_test
            # weighted aggregate MASE：Σ(mae_i · n_i) / Σ(scale_i · n_i)
            if np.isfinite(scale) and scale > 1e-12:
                mase_num += fold_mae * n_test
                mase_den += scale * n_test

        if n_total == 0:
            return {"n": 0, "folds": []}

        return {
            "n": n_total,
            "mae": mae_sum / n_total,
            "rmse": float(np.sqrt(rmse_sumsq / n_total)),
            "mase": mase_num / mase_den if mase_den > 1e-12 else float("inf"),
            "folds": fold_metrics,
        }

    @staticmethod
    def baseline_scores(folds: list[WalkForwardFold], df: pd.DataFrame, target_col: str,
                        methods: list[str] | None = None, m: int = 1) -> dict:
        """同 origin baseline 成績（§18）：model vs same-origin baseline。"""
        methods = methods or ["LAST_VALUE", "ZERO_RETURN", "SEASONAL_NAIVE", "DRIFT"]
        out: dict[str, float] = {}
        for method in methods:
            errs = []
            scales = []
            for fold in folds:
                train_series = df.iloc[list(fold.train_idx)][target_col].to_numpy(dtype=float)
                test_actual = df.iloc[list(fold.test_idx)][target_col].to_numpy(dtype=float)
                pred = baseline_predictions(train_series, len(test_actual), method, m=m)
                errs.extend(np.abs(pred - test_actual))
                scale = naive_scale(train_series, m=m)
                if np.isfinite(scale) and scale > 1e-12:
                    scales.append(scale)
            if errs:
                out[method] = float(np.mean(errs))
        return out


def make_protocol(
    target_family: str,
    target: str,
    date_range: tuple[str, str],
    dataset_semantic: str,
    horizons: list[str] | None = None,
    models: list[str] | None = None,
    baselines: list[str] | None = None,
) -> ProtocolSpec:
    return ProtocolSpec(
        target_family=target_family,
        target=target,
        dataset_semantic=dataset_semantic,
        date_range_start=date_range[0],
        date_range_end=date_range[1],
        horizons=horizons or ["1d"],
        baselines=baselines or ["LAST_VALUE", "ZERO_RETURN", "SEASONAL_NAIVE", "DRIFT"],
        metrics=["MAE", "RMSE", "MASE", "sMAPE", "bias", "median_ae"],
        models=models or [],
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
