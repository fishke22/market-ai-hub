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
    def score(folds: list[WalkForwardFold], df: pd.DataFrame, target_col: str) -> dict:
        """實際值出現後才 score（MAE/RMSE/MASE vs LAST_VALUE baseline）。"""
        actual_all: list[float] = []
        pred_all: list[float] = []
        for fold in folds:
            actual = df.iloc[list(fold.test_idx)][target_col].to_numpy()
            actual_all.extend(float(a) for a in actual)
            pred_all.extend(fold.prediction or ())
        if not actual_all:
            return {"n": 0}
        actual = np.asarray(actual_all)
        pred = np.asarray(pred_all)
        err = pred - actual
        mae = float(np.mean(np.abs(err)))
        rmse = float(np.sqrt(np.mean(err ** 2)))
        # MASE：naive LAST_VALUE baseline 的 in-sample MAE 當 scaling（簡化；正確版應 per-fold）
        last_value_err = np.abs(np.diff(actual, prepend=actual[0]))
        denom = float(np.mean(last_value_err)) if len(last_value_err) else 1.0
        mase = mae / denom if denom > 1e-12 else float("inf")
        return {"n": len(actual), "mae": mae, "rmse": rmse, "mase": mase}


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
