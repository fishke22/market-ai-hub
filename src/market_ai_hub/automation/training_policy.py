"""Phase 2E — 自動學習政策（TrainingEligibilityPolicy）+ River 陰影監測。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

RETRAINABLE_MODELS = ["xgboost", "lightgbm", "nhits", "nbeatsx"]

# Champion 安全：AUTO_PROMOTE_TO_CHAMPION 永遠 false；promotion 需 human approval。
AUTO_PROMOTE_TO_CHAMPION = False


class TrainingEligibilityPolicy:
    """可自動重訓：XGBoost / LightGBM / NHITS / NBEATSx（之後有合格 adapter 才加入其他）。

    不得每預測錯一次就重訓。trigger 至少符合其一：
    1. scheduled weekly retrain AND 有足夠 new labeled observations
    2. River drift warning AND minimum new samples satisfied
    3. model performance degradation AND sample requirement satisfied
    4. manual research request
    """

    def __init__(self, min_new_samples: int = 5, weekly_retrain: bool = True) -> None:
        self.min_new_samples = min_new_samples
        self.weekly_retrain = weekly_retrain

    def eligible_model(self, model: str) -> bool:
        return model in RETRAINABLE_MODELS

    def training_due(
        self,
        model: str,
        new_labeled_observations: int,
        last_train: datetime | None,
        drift_warning: bool = False,
        performance_degraded: bool = False,
        manual_request: bool = False,
    ) -> tuple[bool, str]:
        if not self.eligible_model(model):
            return False, f"{model} not in auto-retrainable set"
        if manual_request:
            return True, "manual research request"
        if new_labeled_observations < self.min_new_samples:
            return False, f"insufficient new samples ({new_labeled_observations}<{self.min_new_samples})"
        if self.weekly_retrain and (last_train is None or (datetime.now(timezone.utc) - last_train) >= timedelta(days=7)):
            return True, "scheduled weekly retrain"
        if drift_warning:
            return True, "river drift warning"
        if performance_degraded:
            return True, "performance degradation"
        return False, "no trigger"


class DriftMonitor:
    """River 陰影：監測 feature/error/regime drift → DRIFT_WARNING（不得 AUTO_PROMOTE）。"""

    def __init__(self, threshold: float = 0.2) -> None:
        self.threshold = threshold

    def psi(self, reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
        ref = np.asarray(reference, dtype=float)
        cur = np.asarray(current, dtype=float)
        if len(ref) < 10 or len(cur) < 10:
            return 0.0
        lo = min(ref.min(), cur.min())
        hi = max(ref.max(), cur.max())
        if hi == lo:
            return 0.0
        edges = np.linspace(lo, hi, bins + 1)
        r, _ = np.histogram(ref, bins=edges)
        c, _ = np.histogram(cur, bins=edges)
        r = r / r.sum() + 1e-9
        c = c / c.sum() + 1e-9
        return float(np.sum((c - r) * np.log(c / r)))

    def check(self, reference: np.ndarray, current: np.ndarray) -> dict:
        p = self.psi(reference, current)
        return {
            "status": "DRIFT_WARNING" if p > self.threshold else "NORMAL",
            "psi": p,
            "retrain_recommended": p > self.threshold,
            "shadow_only": True,
        }
