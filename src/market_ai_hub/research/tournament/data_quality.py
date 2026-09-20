"""Phase 2D.1 — Target Data Quality Validator（frozen target 偵測）。

狀態：VALID / LOW_VARIANCE / FROZEN_TARGET / INSUFFICIENT_DATA / STALE_DATA / INVALID。
FROZEN_TARGET / INSUFFICIENT_DATA / INVALID → 不得進 Tournament ranking，
標 TARGET_DATA_INVALID_FOR_EVALUATION，不得計算具誤導性的 MASE/RMSE rank/winner。
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

ELIGIBLE_FOR_EVALUATION = {"VALID", "LOW_VARIANCE"}


class TargetDataQualityValidator:
    def __init__(self, min_observations: int = 60, max_missing_ratio: float = 0.1,
                 max_consecutive_identical: int = 20, zero_return_ratio_warn: float = 0.8,
                 stale_days: int = 60) -> None:
        self.min_observations = min_observations
        self.max_missing_ratio = max_missing_ratio
        self.max_consecutive_identical = max_consecutive_identical
        self.zero_return_ratio_warn = zero_return_ratio_warn
        self.stale_days = stale_days

    def validate(self, df: pd.DataFrame) -> dict:
        close = pd.to_numeric(df["close"], errors="coerce")
        ts = pd.to_datetime(df["timestamp_utc"], errors="coerce")

        n = len(df)
        metrics = {
            "n_observations": int(n),
            "unique_price_count": int(close.nunique(dropna=True)),
            "price_std": float(close.std()) if n else float("nan"),
            "return_std": float(close.pct_change().std()) if n > 1 else float("nan"),
            "zero_return_ratio": float((close.pct_change() == 0).mean()) if n > 1 else float("nan"),
            "max_consecutive_identical_close": int(self._max_consecutive_identical(close)),
            "missing_ratio": float(close.isna().mean()) if n else float("nan"),
            "timestamp_duplicates": int(ts.duplicated().sum()) if n else 0,
            "first_timestamp": str(ts.min()) if n else None,
            "last_timestamp": str(ts.max()) if n else None,
        }

        status = "VALID"
        reasons: list[str] = []

        if n < self.min_observations:
            status = "INSUFFICIENT_DATA"
            reasons.append(f"n={n} < min_observations={self.min_observations}")
        elif metrics["missing_ratio"] > self.max_missing_ratio:
            status = "INVALID"
            reasons.append(f"missing_ratio={metrics['missing_ratio']:.3f}")
        elif metrics["timestamp_duplicates"] > 0:
            status = "INVALID"
            reasons.append(f"timestamp_duplicates={metrics['timestamp_duplicates']}")
        elif metrics["unique_price_count"] <= 1 or metrics["price_std"] == 0:
            status = "FROZEN_TARGET"
            reasons.append("price constant (unique<=1 or std=0)")
        elif metrics["max_consecutive_identical_close"] > self.max_consecutive_identical:
            status = "FROZEN_TARGET"
            reasons.append(f"max_consecutive_identical={metrics['max_consecutive_identical_close']}")
        elif metrics["zero_return_ratio"] > self.zero_return_ratio_warn:
            status = "LOW_VARIANCE"
            reasons.append(f"zero_return_ratio={metrics['zero_return_ratio']:.3f}")

        # stale（最後時間戳過舊）
        if status == "VALID" and metrics["last_timestamp"]:
            try:
                last = pd.Timestamp(metrics["last_timestamp"])
                if last.tzinfo is None:
                    last = last.tz_localize("UTC")
                age_days = (pd.Timestamp.now("UTC") - last).days
                if age_days > self.stale_days:
                    status = "STALE_DATA"
                    reasons.append(f"last_timestamp {age_days}d old")
            except Exception:
                pass

        eligible = status in ELIGIBLE_FOR_EVALUATION
        return {
            "status": status,
            "eligible_for_evaluation": eligible,
            "evaluation_gate": "OK" if eligible else "TARGET_DATA_INVALID_FOR_EVALUATION",
            "reasons": reasons,
            "metrics": metrics,
        }

    @staticmethod
    def _max_consecutive_identical(s: pd.Series) -> int:
        if len(s) == 0:
            return 0
        best = cur = 1
        arr = s.to_numpy()
        for i in range(1, len(arr)):
            if arr[i] == arr[i - 1]:
                cur += 1
                best = max(best, cur)
            else:
                cur = 1
        return best
